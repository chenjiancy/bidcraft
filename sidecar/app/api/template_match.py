"""模板匹配与语义比对 API（Task 18）。"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_engine, get_session
from app.db.session import session_factory
from app.parse import template_match as tm
from app.parse.service import job_manager
from app.repositories.base import NotFoundError, Scope
from app.repositories.project import ProjectRepository
from app.repositories.template_compare import TemplateCompareRepository

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])


SessionDep = Annotated[Session, Depends(get_session)]


def _get_project_or_404(session: Session, enterprise_id: str, project_id: str) -> None:
    try:
        ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


# ---------- Schema ----------


class AutoMatchResult(BaseModel):
    best_match: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    has_match: bool = False
    threshold: int = 90
    error: str | None = None


class CopyTemplatesIn(BaseModel):
    template_ids: list[str] = Field(..., min_length=1)


class FindingsUpdateIn(BaseModel):
    """单条 finding 裁决更新。"""

    finding_id: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^(update|replace|manual_review|keep)$")
    note: str | None = Field(default=None, max_length=500)


class BatchConfirmIn(BaseModel):
    finding_ids: list[str] = Field(..., min_length=1)
    action: str = Field(..., pattern="^(update|replace|keep)$")
    note: str | None = Field(default=None, max_length=500)


# ---------- 端点 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/status",
)
def get_template_match_status(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """查询当前模板比对状态。"""
    _get_project_or_404(session, enterprise_id, project_id)
    try:
        return tm.get_compare_status(session_factory(get_engine()), enterprise_id, project_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/enter",
)
def enter_template_matching(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """进入模板匹配阶段（MATERIAL_CONFIRMED → TEMPLATE_MATCHED）。"""
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")
    try:
        return tm.enter_template_matching(session_factory(get_engine()), enterprise_id, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/auto-match",
    response_model=AutoMatchResult,
)
def auto_match_templates(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """自动匹配企业模板库（按 agency/doc_type + 章节结构计算相似度）。"""
    _get_project_or_404(session, enterprise_id, project_id)
    try:
        result = tm.auto_match_templates(enterprise_id, project_id)
        return AutoMatchResult(**result).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/copy",
)
def copy_templates_to_work(
    enterprise_id: str,
    project_id: str,
    body: CopyTemplatesIn,
    session: SessionDep,
) -> dict[str, Any]:
    """手动指定模板：复制模板文件集到项目 template-work/（多模板组合支持）。"""
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")
    try:
        work_dir_rel, copied = tm.copy_templates_to_work(
            enterprise_id, project_id, body.template_ids
        )
        return {"work_dir": work_dir_rel, "copied": copied}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/run-compare",
)
def run_template_compare(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """执行模板比对：关联 + 语义 diff + 机械检查，写入 template_compare 记录。"""
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")

    from app.db.deps import get_engine as _get_engine
    from app.db.session import session_factory as _sess_factory

    with _sess_factory(_get_engine())() as s:
        scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
        tc_repo = TemplateCompareRepository(s, scope)

        # 获取当前比对记录或新建
        tc = tc_repo.get_by_project()
        if tc is None:
            tc = tc_repo.create(
                enterprise_id=enterprise_id,
                project_id=project_id,
                match_method="manual",
                work_dir=str(tm.path_utils.template_work_dir(enterprise_id, project_id)),
            )
            s.commit()

    # 加载关联章节
    tpl_chapters: dict[str, Any] = {}
    associations: list[dict[str, Any]] = []

    # 从 template-work/ 子目录收集章节
    work_dir = tm.path_utils.template_work_dir(enterprise_id, project_id)
    parsed_chapters: dict[str, Any] = {}

    # 从 chapters.json 读取解析侧章节
    chapters_path = tm.path_utils.chapters_path(enterprise_id, project_id)
    parse_chapter_names: list[str] = []
    if chapters_path.is_file():
        cp = json.loads(chapters_path.read_text(encoding="utf-8"))
        for src in cp.get("sources", []):
            for sec in src.get("sections", []):
                parse_chapter_names.append(sec.get("name") or sec.get("title", ""))

    # 收集模板章节和 parsed 章节路径
    for sub in work_dir.iterdir():
        if not sub.is_dir():
            continue
        for ver_dir in sub.iterdir():
            if not ver_dir.is_dir():
                continue
            tpl_json = ver_dir / "template.json"
            if not tpl_json.is_file():
                continue
            try:
                meta = json.loads(tpl_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            for stem in meta.get("chapters", []):
                for ext in (".docx", ".doc"):
                    p = ver_dir / f"{stem}{ext}"
                    if p.is_file():
                        tpl_chapters[stem] = p
                        break

    # 从 parsed/docx/ 收集已导出的章节
    docx_dir = tm.path_utils.docx_dir(enterprise_id, project_id)
    if docx_dir.is_dir():
        for src_sub in docx_dir.iterdir():
            if not src_sub.is_dir():
                continue
            for docx_file in src_sub.glob("*.docx"):
                parsed_chapters[src_sub.name] = docx_file
                if src_sub.name not in parse_chapter_names:
                    parse_chapter_names.append(src_sub.name)

    # 构建关联
    associations, unmatched = tm.build_association(parse_chapter_names, list(tpl_chapters.keys()))

    # Schema 门禁校验
    schema_ok, schema_errors = tm.validate_template_schema(work_dir)
    if not schema_ok:
        raise HTTPException(
            status_code=400,
            detail=f"Schema 校验失败（BP-3），无法进入比对：{schema_errors[:5]}",
        )

    # 执行比对
    findings, bp4_results = tm.run_comparison(parsed_chapters, tpl_chapters, associations)

    # 保存
    from app.db.deps import get_engine as _ge2
    from app.db.session import session_factory as _sf2

    with _sf2(_ge2())() as s:
        scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
        tc_repo = TemplateCompareRepository(s, scope)
        tc = tc_repo.get_by_project()
        if tc is None:
            tc = tc_repo.create(
                enterprise_id=enterprise_id,
                project_id=project_id,
                match_method="manual",
                work_dir=str(work_dir),
            )
        tc_repo.update(
            tc.id,
            findings_json=json.dumps(findings, ensure_ascii=False),
            association_json=json.dumps(associations, ensure_ascii=False),
            status="matched",
            bp4_summary_json=json.dumps(bp4_results, ensure_ascii=False),
        )
        s.commit()

    return {
        "compare_id": tc.id,
        "findings_count": len(findings),
        "unmatched_count": len(unmatched),
        "findings": findings,
        "associations": associations,
        "schema_valid": schema_ok,
        "schema_errors": schema_errors,
    }


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/findings/{finding_id}/resolve",
)
def resolve_finding(
    enterprise_id: str,
    project_id: str,
    finding_id: str,
    body: FindingsUpdateIn,
    session: SessionDep,
) -> dict[str, Any]:
    """裁决单条 finding（update/replace/manual_review/keep）。"""
    _get_project_or_404(session, enterprise_id, project_id)
    from app.db.deps import get_engine as _ge
    from app.db.session import session_factory as _sf

    with _sf(_ge())() as s:
        scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
        tc_repo = TemplateCompareRepository(s, scope)
        tc = tc_repo.get_by_project()
        if tc is None:
            raise HTTPException(status_code=404, detail="比对记录不存在")

        findings = json.loads(tc.findings_json) if tc.findings_json else []
        found = False
        for f in findings:
            if f.get("id") == finding_id:
                f["resolved_action"] = body.action
                f["resolved_note"] = body.note
                f["resolved_at"] = tm._now_iso()
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail=f"finding {finding_id} 不存在")

        rejected = sum(1 for f in findings if f.get("resolved_action") == "manual_review")
        accepted = sum(
            1 for f in findings if f.get("resolved_action") in ("update", "replace", "keep")
        )
        tc_repo.update(
            tc.id,
            findings_json=json.dumps(findings, ensure_ascii=False),
            rejected_count=rejected,
            accepted_count=accepted,
        )
        s.commit()

    return {"updated": finding_id, "action": body.action}


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/batch-confirm",
)
def batch_confirm_findings(
    enterprise_id: str,
    project_id: str,
    body: BatchConfirmIn,
    session: SessionDep,
) -> dict[str, Any]:
    """批量确认 finding（高置信批量通过）。"""
    _get_project_or_404(session, enterprise_id, project_id)
    from app.db.deps import get_engine as _ge
    from app.db.session import session_factory as _sf

    with _sf(_ge())() as s:
        scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
        tc_repo = TemplateCompareRepository(s, scope)
        tc = tc_repo.get_by_project()
        if tc is None:
            raise HTTPException(status_code=404, detail="比对记录不存在")

        findings = json.loads(tc.findings_json) if tc.findings_json else []
        confirmed_ids = set(body.finding_ids)
        updated = 0
        for f in findings:
            if f.get("id") in confirmed_ids:
                f["resolved_action"] = body.action
                f["resolved_note"] = body.note
                f["resolved_at"] = tm._now_iso()
                updated += 1

        rejected = sum(1 for f in findings if f.get("resolved_action") == "manual_review")
        accepted = sum(
            1 for f in findings if f.get("resolved_action") in ("update", "replace", "keep")
        )
        tc_repo.update(
            tc.id,
            findings_json=json.dumps(findings, ensure_ascii=False),
            rejected_count=rejected,
            accepted_count=accepted,
        )
        s.commit()

    return {"confirmed_count": updated, "total_findings": len(findings)}


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/review",
)
def enter_template_review(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """TEMPLATE_MATCHED → TEMPLATE_REVIEW：完成比对，进入差异确认阶段。"""
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")
    from app.db.deps import get_engine as _ge
    from app.db.session import session_factory as _sf

    with _sf(_ge())() as s:
        scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
        tc_repo = TemplateCompareRepository(s, scope)
        tc = tc_repo.get_by_project()
        compare_id = tc.id if tc else None

    try:
        return tm.enter_template_review(
            session_factory(get_engine()), enterprise_id, project_id, compare_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/confirm",
)
def confirm_template_review(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """TEMPLATE_REVIEW → READY_TO_RENDER：差异全部裁决完成。"""
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")
    try:
        return tm.confirm_template_review(session_factory(get_engine()), enterprise_id, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/template-match/invalidate",
)
def invalidate_compare(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """回退比对：上游重解析使比对作废，回退到 MATERIAL_CONFIRMED。"""
    _get_project_or_404(session, enterprise_id, project_id)
    if job_manager.is_running(enterprise_id, project_id):
        raise HTTPException(status_code=409, detail="该项目解析任务正在运行")
    try:
        tm.invalidate_template_compare(
            session_factory(get_engine()), enterprise_id, project_id, reason="upstream_reset"
        )
        return {"invalidated": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
