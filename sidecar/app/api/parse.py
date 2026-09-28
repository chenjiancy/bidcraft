"""招标文件解析 API（Task 8）。

- POST   /projects/{pid}/parse/sources  登记源文件（本机路径 → 复制入项目 source/）
- POST   /projects/{pid}/parse/start    启动/断点续跑解析（SSE 进度流）
- GET    /projects/{pid}/parse/status   解析状态 + checkpoint + 章节概况
- POST   /projects/{pid}/parse/retry    单项重置（随后调 start 续跑）
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
from app.parse import engine as mineru_engine
from app.parse import preprocess, service
from app.parse.service import JobRunningError, ParseError, job_manager
from app.repositories.base import NotFoundError, Scope
from app.repositories.project import ProjectRepository
from app.schemas.parse import (
    EngineStatusOut,
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
