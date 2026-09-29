"""招标文件解析 API（Task 8）。

- POST   /projects/{pid}/parse/sources  登记源文件（本机路径 → 复制入项目 source/）
- POST   /projects/{pid}/parse/start    启动/断点续跑解析（SSE 进度流）
- GET    /projects/{pid}/parse/status   解析状态 + checkpoint + 章节概况
- POST   /projects/{pid}/parse/retry    单项重置（随后调 start 续跑）
- GET    /projects/{pid}/parse/config   解析配置（未设置返回默认，Task 9）
- PUT    /projects/{pid}/parse/config   保存项目级解析配置（Task 9）
- GET    /parse/engine                  MinerU/LibreOffice 引擎可用性检测

企业级隔离：所有项目操作经 enterprise_id scope 校验（仓储层 NotFound 即 404）。
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_engine, get_session
from app.db.session import session_factory
from app.parse import config as parse_config_mod
from app.parse import engine as mineru_engine
from app.parse import preprocess, service
from app.parse import state as parse_state
from app.parse.config import ConfigError
from app.parse.service import JobRunningError, ParseError, job_manager
from app.repositories.app_event import AppEventRepository
from app.repositories.base import NotFoundError, Scope
from app.repositories.parse_config import ParseConfigRepository
from app.repositories.project import ProjectRepository
from app.schemas.parse import (
    EngineStatusOut,
    ParseConfigItemOut,
    ParseConfigOut,
    ParseConfigSavedOut,
    ParseConfigUpdate,
    ParseRetryIn,
    ParseStartIn,
    ParseStatusOut,
    RegisterSourcesIn,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])

SessionDep = Annotated[Session, Depends(get_session)]


def _get_project_or_404(session: Session, enterprise_id: str, project_id: str) -> None:
    try:
        ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


# ---------- 引擎检测 ----------


@router.get("/parse/engine", response_model=EngineStatusOut)
async def parse_engine() -> EngineStatusOut:
    status = await mineru_engine.probe_status()
    return EngineStatusOut(
        available=status.available,
        python_path=status.python_path,
        version=status.version,
        cuda_available=status.cuda_available,
        cuda_device=status.cuda_device,
        error=status.error,
        libreoffice_available=preprocess.soffice_available(),
    )


# ---------- 源文件登记 ----------


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/parse/sources",
    status_code=201,
)
def register_sources(
    enterprise_id: str,
    project_id: str,
    body: RegisterSourcesIn,
    session: SessionDep,
) -> dict[str, object]:
    _get_project_or_404(session, enterprise_id, project_id)
    try:
        result = service.register_sources(
            session_factory(get_engine()),
            enterprise_id,
            project_id,
            [f.model_dump() for f in body.files],
        )
    except JobRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return result


# ---------- 启动解析（SSE） ----------


@router.post("/enterprises/{enterprise_id}/projects/{project_id}/parse/start")
async def parse_start(
    enterprise_id: str,
    project_id: str,
    body: ParseStartIn,
    session: SessionDep,
) -> StreamingResponse:
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    def emit(event: dict[str, object]) -> None:
        queue.put_nowait(event)

    def coro_factory(task_id: str):
        return service.run_parse(
            session_factory(get_engine()),
            enterprise_id,
            project_id,
            task_id,
            reparse=body.reparse,
            emit=emit,
            api_key=body.api_key,
        )

    try:
        _task, task_id = job_manager.start(enterprise_id, project_id, coro_factory)
    except JobRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    async def generate() -> AsyncIterator[bytes]:
        # 任务与流解耦：客户端断连不杀任务（checkpoint 落盘，可经 status 查询/续跑）
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
            if event.get("stage") in ("completed", "failed", "cancelled"):
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Task-Id": task_id},
    )


# ---------- 状态查询 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/parse/status",
    response_model=ParseStatusOut,
)
def parse_status(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, object]:
    _get_project_or_404(session, enterprise_id, project_id)
    try:
        return service.get_status(session_factory(get_engine()), enterprise_id, project_id)
    except ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


# ---------- 解析配置（Task 9） ----------


def _config_to_out(cfg: parse_config_mod.ParseConfig, *, is_default: bool) -> ParseConfigOut:
    selected = cfg.items
    return ParseConfigOut(
        is_default=is_default,
        items=[
            ParseConfigItemOut(
                key=entry["key"],
                label=entry["label"],
                required=entry["required"],
                selected=bool(selected.get(entry["key"], entry["required"])),
            )
            for entry in parse_config_mod.catalog()
        ],
        llm_enabled=cfg.llm_enabled,
        llm_mode=cfg.llm_mode,
    )


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/parse/config",
    response_model=ParseConfigOut,
)
def get_parse_config(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> ParseConfigOut:
    """读取项目级解析配置；从未保存时返回默认配置（is_default=true）。"""
    _get_project_or_404(session, enterprise_id, project_id)
    repo = ParseConfigRepository(session, Scope(enterprise_id=enterprise_id))
    payload = repo.get_payload(project_id)
    cfg = parse_config_mod.from_payload(payload)
    return _config_to_out(cfg, is_default=payload is None)


@router.put(
    "/enterprises/{enterprise_id}/projects/{project_id}/parse/config",
    response_model=ParseConfigSavedOut,
)
def update_parse_config(
    enterprise_id: str,
    project_id: str,
    body: ParseConfigUpdate,
    session: SessionDep,
) -> ParseConfigSavedOut:
    """保存项目级解析配置。

    - 解析任务运行中拒绝（409）；
    - 关键项取消/未知项/模式非法拒绝（400）；
    - 实际发生变更写 app_event（parse_config_change，TR-9.4 操作日志）；
    - PARSED 后变更返回 reparse_required=true（物理层 checkpoint 不受影响；
      affected_items 为 Task 10 要素提取项 extract:coarse/extract:llm，
      前端据此做单项重试而非整跑）。
    """
    try:
        project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="解析任务运行中，不能修改配置")

    try:
        new_cfg = parse_config_mod.build_config(
            body.selected, llm_enabled=body.llm_enabled, llm_mode=body.llm_mode
        )
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    repo = ParseConfigRepository(session, Scope(enterprise_id=enterprise_id))
    old_cfg = parse_config_mod.from_payload(repo.get_payload(project_id))
    changes = parse_config_mod.diff_configs(old_cfg, new_cfg)

    if changes:
        repo.upsert(project_id, new_cfg.model_dump())
        AppEventRepository(session, Scope(enterprise_id=enterprise_id)).record(
            "parse_config_change", project_id, {"changes": changes}
        )
        session.commit()

    affected = list(parse_config_mod.affected_checkpoint_items(changes))
    # 与 checkpoint 实有项求交（extract:llm 仅在校验模式注册过才存在）
    if affected:
        ckpt_path = service.paths.checkpoints_dir(enterprise_id, project_id) / (
            f"{service.JOB_TYPE}.json"
        )
        if ckpt_path.is_file():
            store = service.CheckpointStore.load_or_create(ckpt_path, service.JOB_TYPE, {})
            affected = [k for k in affected if k in store.items]
        else:
            affected = []
    reparse_required = bool(changes) and project.parse_status in (
        parse_state.PARSED,
        parse_state.SCORE_PARSED,
    )
    return ParseConfigSavedOut(
        config=_config_to_out(new_cfg, is_default=False),
        reparse_required=reparse_required,
        changes=changes,
        affected_items=affected,
    )


# ---------- 单项重试（重置 checkpoint 项，随后 start 续跑） ----------


@router.post("/enterprises/{enterprise_id}/projects/{project_id}/parse/retry")
def parse_retry(
    enterprise_id: str,
    project_id: str,
    body: ParseRetryIn,
    session: SessionDep,
) -> dict[str, object]:
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")
    try:
        service.reset_item(enterprise_id, project_id, body.item)
    except ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"reset": True, "item": body.item}
