"""渲染 API（Task 19）。

端点：
- GET    /enterprises/{eid}/projects/{pid}/render/plan      渲染计划查询
- POST   /enterprises/{eid}/projects/{pid}/render/confirm   计划统一确认（含取值调整）
- POST   /enterprises/{eid}/projects/{pid}/render/start     启动渲染（SSE 进度流）
- POST   /enterprises/{eid}/projects/{pid}/render/cancel    取消渲染
- GET    /enterprises/{eid}/projects/{pid}/render/status    渲染进度查询
- POST   /enterprises/{eid}/projects/{pid}/render/retry     单项重渲染
- GET    /enterprises/{eid}/projects/{pid}/render/warnings  警告清单
- GET    /enterprises/{eid}/projects/{pid}/render/audit     一致性审计结果
- GET    /enterprises/{eid}/projects/{pid}/render/download/{chapter}  下载渲染产物
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_engine, get_session
from app.db.session import session_factory
from app.parse import paths as p
from app.parse.state import (
    EXPORTED,
    READY_TO_RENDER,
    RENDERED,
    RENDERING,
    ensure_transition,
)
from app.render import service as render_service
from app.render.service import PlaceholderInfo
from app.repositories.base import NotFoundError, Scope
from app.repositories.generated_doc import GeneratedDocRepository
from app.repositories.project import ProjectRepository
from app.schemas.render import (
    AuditResultOut,
    ConfirmRenderPlanIn,
    ConfirmRenderPlanOut,
    ConsistencyIssueOut,
    ExportStatusOut,
    PlaceholderInfoOut,
    RenderPlanItemOut,
    RenderPlanOut,
    RenderStartIn,
    RenderStatusOut,
    TermIssueOut,
    WarningItemOut,
    WarningListOut,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])

SessionDep = Annotated[Session, Depends(get_session)]


def _get_project_or_404(session: Session, enterprise_id: str, project_id: str) -> None:
    try:
        ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


# 渲染任务全局注册表（enterprise_id + project_id → 取消信号）
_render_jobs: dict[str, dict[str, threading.Event]] = {}
_jobs_lock = threading.Lock()


def _job_key(enterprise_id: str, project_id: str) -> str:
    return f"{enterprise_id}:{project_id}"


def _cancel_event_for(enterprise_id: str, project_id: str) -> threading.Event:
    key = _job_key(enterprise_id, project_id)
    with _jobs_lock:
        evt = _render_jobs.get(key, {}).get("cancel")
        if evt is None:
            evt = threading.Event()
            _render_jobs[key] = {"cancel": evt}
        return evt


def _clear_job(enterprise_id: str, project_id: str) -> None:
    key = _job_key(enterprise_id, project_id)
    with _jobs_lock:
        _render_jobs.pop(key, None)


# ---------- 1. 渲染计划查询 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/plan",
    response_model=RenderPlanOut,
)
def render_plan(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> RenderPlanOut:
    """生成并返回渲染计划。"""
    _get_project_or_404(session, enterprise_id, project_id)

    items = render_service.generate_render_plan(enterprise_id, project_id)
    missing_total = sum(it.missing_count for it in items)

    out_items = [
        RenderPlanItemOut(
            chapter=it.chapter,
            seq=it.seq,
            template_path=it.template_path,
            placeholders=[
                PlaceholderInfoOut(
                    name=ph.name,
                    type=ph.type,
                    description=ph.description,
                    value=ph.value,
                    needs_manual=ph.needs_manual,
                    is_missing=ph.is_missing,
                )
                for ph in it.placeholders
            ],
            missing_count=it.missing_count,
        )
        for it in items
    ]

    return RenderPlanOut(plan=out_items, total=len(out_items), missing_total=missing_total)


# ---------- 2. 计划统一确认 ----------


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/confirm",
    response_model=ConfirmRenderPlanOut,
)
def confirm_render_plan(
    enterprise_id: str,
    project_id: str,
    body: ConfirmRenderPlanIn,
    session: SessionDep,
) -> ConfirmRenderPlanOut:
    """保存 B 类人工调整值，确保状态处于 READY_TO_RENDER。"""
    _get_project_or_404(session, enterprise_id, project_id)

    # 读取当前项目状态
    project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)

    current = project.parse_status
    if current not in (READY_TO_RENDER, RENDERED):
        raise HTTPException(
            status_code=409,
            detail=f"当前状态 {current} 不允许确认渲染计划",
        )

    # 保存人工取值到 render_plan.json（在计划数据中叠加 b_class_overrides）
    plan_data = render_service._read_json(p.render_plan_path(enterprise_id, project_id))
    if not plan_data:
        # 先生成计划
        render_service.generate_render_plan(enterprise_id, project_id)
        plan_data = render_service._read_json(p.render_plan_path(enterprise_id, project_id))

    # 将 B 类调整值写入计划
    if body.b_class_adjustments:
        for adj in body.b_class_adjustments:
            for item in plan_data:
                for ph in item.get("placeholders", []):
                    if ph.get("name") == adj.placeholder:
                        ph["value"] = adj.value
                        ph["needs_manual"] = False
                        break

    render_service._atomic_write_json(p.render_plan_path(enterprise_id, project_id), plan_data)

    # 如果当前是 RENDERED，回退到 READY_TO_RENDER
    if current == RENDERED:
        ensure_transition(current, READY_TO_RENDER)
        project.parse_status = READY_TO_RENDER
        session.commit()

    # 统计
    total_ph = sum(len(it.get("placeholders", [])) for it in plan_data)
    b_needs_manual = sum(
        1
        for it in plan_data
        for ph in it.get("placeholders", [])
        if ph.get("type") == "b_class" and ph.get("needs_manual")
    )
    missing = sum(it.get("missing_count", 0) for it in plan_data)

    return ConfirmRenderPlanOut(
        status=READY_TO_RENDER,
        total_placeholders=total_ph,
        b_class_needs_manual=b_needs_manual,
        missing_count=missing,
    )


# ---------- 3. 启动渲染（SSE） ----------


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/start",
)
async def render_start(
    enterprise_id: str,
    project_id: str,
    body: RenderStartIn,
    session: SessionDep,
) -> StreamingResponse:
    """启动逐章渲染，以 SSE 推送进度事件。"""
    _get_project_or_404(session, enterprise_id, project_id)

    project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)

    current = project.parse_status
    if current != READY_TO_RENDER:
        raise HTTPException(
            status_code=409,
            detail=f"当前状态 {current}，仅 READY_TO_RENDER 可启动渲染",
        )

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    def emit(event: dict[str, object]) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    cancel_evt = _cancel_event_for(enterprise_id, project_id)

    def _render_worker() -> None:
        try:
            emit({"type": "progress", "event": "started"})
            paths = render_service.render_all(enterprise_id, project_id, cancel_event=cancel_evt)
            if cancel_evt.is_set():
                emit({"type": "progress", "event": "cancelled"})
            else:
                emit({"type": "progress", "event": "completed", "paths": [str(p) for p in paths]})
        except Exception as exc:
            emit({"type": "error", "message": str(exc)[:500]})
        finally:
            _clear_job(enterprise_id, project_id)

    # 启动后台线程
    import threading as _td  # noqa: PLC0415

    worker = _td.Thread(target=_render_worker, daemon=True)
    worker.start()

    async def generate() -> AsyncIterator[bytes]:
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
            if event.get("type") in ("completed", "cancelled", "error"):
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


# ---------- 4. 取消渲染 ----------


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/cancel",
)
def render_cancel(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, object]:
    """发送取消信号。"""
    _get_project_or_404(session, enterprise_id, project_id)
    evt = _cancel_event_for(enterprise_id, project_id)
    evt.set()
    return {"cancelled": True}


# ---------- 5. 渲染进度查询 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/status",
    response_model=RenderStatusOut,
)
def render_status(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> RenderStatusOut:
    """查询渲染进度。"""
    _get_project_or_404(session, enterprise_id, project_id)

    project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
    status = project.parse_status

    ckpt = render_service._read_json(p.render_checkpoint_path(enterprise_id, project_id)) or {}
    current_chapter = ckpt.get("current_chapter")
    completed = ckpt.get("completed", [])

    # 从 GeneratedDoc 表统计已完成的章节
    scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
    gd_repo = GeneratedDocRepository(session, scope)
    records = gd_repo.list_by_project()
    success_chapters = [r.chapter for r in records if r.status == "success"]

    return RenderStatusOut(
        parse_status=status,
        rendering=status == RENDERING,
        current_chapter=current_chapter,
        completed_chapters=completed + [c for c in success_chapters if c not in completed],
        total_chapters=len(success_chapters) + len(completed),
        error_msg=ckpt.get("error"),
    )


# ---------- 6. 单项重渲染 ----------


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/retry",
)
def render_retry(
    enterprise_id: str,
    project_id: str,
    chapter: str,
    session: SessionDep,
) -> dict[str, object]:
    """重渲染指定章节。"""
    _get_project_or_404(session, enterprise_id, project_id)

    project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
    if project.parse_status not in (READY_TO_RENDER, RENDERING, RENDERED):
        raise HTTPException(
            status_code=409,
            detail=f"当前状态 {project.parse_status} 不允许重渲染",
        )

    # 读取渲染计划
    plan_data = render_service._read_json(p.render_plan_path(enterprise_id, project_id))
    if not plan_data:
        raise HTTPException(status_code=400, detail="渲染计划不存在，请先查询计划")

    target = next((it for it in plan_data if it.get("chapter") == chapter), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"章节 {chapter} 不在渲染计划中")

    # 清除该章节旧记录
    scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
    gd_repo = GeneratedDocRepository(session, scope)
    existing = gd_repo.get_by_chapter(chapter)
    if existing is not None:
        session.delete(existing)
        session.commit()

    # 重新渲染该章节
    engine = get_engine()
    sess = session_factory(engine)()
    try:
        a_context = render_service.build_a_class_context(enterprise_id, project_id, sess)
        plan_item = render_service.RenderPlanItem(
            chapter=chapter,
            seq=target["seq"],
            template_path=target["template_path"],
            placeholders=[
                PlaceholderInfo(
                    name=ph["name"],
                    type=ph["type"],
                    description=ph.get("description", ""),
                    is_missing=ph.get("is_missing", False),
                )
                for ph in target.get("placeholders", [])
            ],
            missing_count=target.get("missing_count", 0),
        )
        output_path = render_service.render_chapter(
            enterprise_id, project_id, plan_item, a_context, sess
        )
        return {"chapter": chapter, "output_path": str(output_path), "re_rendered": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        sess.close()


# ---------- 7. 警告清单 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/warnings",
    response_model=WarningListOut,
)
def render_warnings(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> WarningListOut:
    """获取渲染警告清单。"""
    _get_project_or_404(session, enterprise_id, project_id)

    warnings = render_service.build_warning_list(enterprise_id, project_id)

    out_warnings = [
        WarningItemOut(
            chapter=w.chapter,
            placeholder=w.placeholder,
            problem_type=w.problem_type,  # type: ignore[arg-type]
            suggestion=w.suggestion,
        )
        for w in warnings
    ]

    return WarningListOut(
        warnings=out_warnings,
        total=len(out_warnings),
        missing_text=sum(1 for w in out_warnings if w.problem_type == "missing_text"),
        missing_image=sum(1 for w in out_warnings if w.problem_type == "missing_image"),
        b_class_uncertain=sum(1 for w in out_warnings if w.problem_type == "b_class_uncertain"),
    )


# ---------- 8. 一致性审计 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/audit",
    response_model=AuditResultOut,
)
def render_audit(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> AuditResultOut:
    """获取一致性审计结果。"""
    _get_project_or_404(session, enterprise_id, project_id)

    result = render_service.run_consistency_audit(enterprise_id, project_id)

    return AuditResultOut(
        doc_type=result.get("doc_type", "bid"),
        term_issues=[TermIssueOut(**i) for i in result.get("term_issues", [])],
        consistency_issues=[ConsistencyIssueOut(**i) for i in result.get("consistency_issues", [])],
        summary=result.get("summary", ""),
    )


# ---------- 9. 下载渲染产物 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/download/{chapter}",
)
def render_download(
    enterprise_id: str,
    project_id: str,
    chapter: str,
    session: SessionDep,
) -> StreamingResponse:
    """下载指定章节的渲染产物 Word 文件。"""
    _get_project_or_404(session, enterprise_id, project_id)

    scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
    gd_repo = GeneratedDocRepository(session, scope)
    rec = gd_repo.get_by_chapter(chapter)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"章节 {chapter} 无渲染产物")
    if rec.status != "success":
        raise HTTPException(status_code=400, detail=f"章节 {chapter} 渲染状态: {rec.status}")

    base_dir = p.project_dir(enterprise_id, project_id)
    file_path = base_dir / rec.file_path
    # M13 修复：路径穿越防护
    from app.parse.paths import ensure_within_project

    ensure_within_project(base_dir, file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {rec.file_path}")

    def file_iter() -> Any:
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_iter(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{chapter}.docx"'},
    )


# ---------- 10. PDF 导出（Task 20） ----------

_export_jobs: dict[str, threading.Event] = {}
_export_lock = threading.Lock()


def _export_job_key(enterprise_id: str, project_id: str) -> str:
    return f"export:{enterprise_id}:{project_id}"


def _export_cancel_event(enterprise_id: str, project_id: str) -> threading.Event:
    key = _export_job_key(enterprise_id, project_id)
    with _export_lock:
        evt = _export_jobs.get(key)
        if evt is None:
            evt = threading.Event()
            _export_jobs[key] = evt
        return evt


def _clear_export_job(enterprise_id: str, project_id: str) -> None:
    key = _export_job_key(enterprise_id, project_id)
    with _export_lock:
        _export_jobs.pop(key, None)


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/export",
)
async def render_export(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> StreamingResponse:
    """启动 PDF 导出（转 PDF + 合并），以 SSE 推送进度事件。"""
    _get_project_or_404(session, enterprise_id, project_id)

    project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
    if project.parse_status != RENDERED:
        raise HTTPException(
            status_code=409,
            detail=f"当前状态 {project.parse_status}，仅 RENDERED 可导出",
        )

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    def emit(event: dict[str, object]) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    cancel_evt = _export_cancel_event(enterprise_id, project_id)

    def _export_worker() -> None:
        try:
            emit({"type": "progress", "stage": "started"})
            result = render_service.export_pdf(
                enterprise_id, project_id, cancel_event=cancel_evt, emit=emit
            )
            if cancel_evt.is_set():
                emit({"type": "progress", "stage": "cancelled"})
            elif result.get("success"):
                emit(
                    {
                        "type": "progress",
                        "stage": "completed",
                        "merged_path": result.get("merged_path", ""),
                        "total_chapters": result.get("total_chapters", 0),
                    }
                )
            else:
                emit(
                    {
                        "type": "error",
                        "message": result.get("error", "导出失败"),
                    }
                )
        except Exception as exc:
            emit({"type": "error", "message": str(exc)[:500]})
        finally:
            _clear_export_job(enterprise_id, project_id)

    import threading as _td  # noqa: PLC0415

    worker = _td.Thread(target=_export_worker, daemon=True)
    worker.start()

    async def generate() -> AsyncIterator[bytes]:
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
            if event.get("type") in ("completed", "cancelled", "error"):
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/export/cancel",
)
def render_export_cancel(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, object]:
    """发送导出取消信号。"""
    _get_project_or_404(session, enterprise_id, project_id)
    evt = _export_cancel_event(enterprise_id, project_id)
    evt.set()
    return {"cancelled": True}


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/export/status",
    response_model=ExportStatusOut,
)
def render_export_status(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> ExportStatusOut:
    """查询导出状态。"""
    _get_project_or_404(session, enterprise_id, project_id)

    project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)

    # 检查是否有活跃的导出任务（通过事件是否已 set 判断）
    key = _export_job_key(enterprise_id, project_id)
    with _export_lock:
        evt = _export_jobs.get(key)
        is_exporting = evt is not None and not evt.is_set()

    # 检查合并 PDF 是否已存在
    merged_path = p.pdf_dir(enterprise_id, project_id) / "标书.pdf"
    has_merged = merged_path.exists()

    if project.parse_status == EXPORTED or has_merged:
        export_status = "completed"
    elif is_exporting:
        export_status = "exporting"
    else:
        export_status = "idle"

    return ExportStatusOut(
        export_status=export_status,
        merged_path=str(merged_path) if has_merged else None,
        total_chapters=0,
        current_chapter=None,
        error_msg=None,
    )


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/render/export/pdf",
)
def render_export_pdf_download(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> StreamingResponse:
    """下载合并后的完整 PDF。"""
    _get_project_or_404(session, enterprise_id, project_id)

    merged_path = p.pdf_dir(enterprise_id, project_id) / "标书.pdf"
    if not merged_path.exists():
        raise HTTPException(status_code=404, detail="合并 PDF 不存在")

    def file_iter() -> Any:
        with merged_path.open("rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_iter(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="标书.pdf"'},
    )
