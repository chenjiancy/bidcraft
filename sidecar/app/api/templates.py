"""模板库 API（Task 17）。

路由前缀：/api/v1/enterprises/{enterprise_id}/templates
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_session
from app.repositories.base import NotFoundError, Scope
from app.repositories.template import TemplateRepository
from app.schemas.template import (
    ComplianceResult,
    TemplateCreateIn,
    TemplateDeleteOut,
    TemplateListOut,
    TemplateNewVersionIn,
    TemplateOut,
    TemplateUpdateIn,
)
from app.templates import service as svc

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])
SessionDep = Annotated[Session, Depends(get_session)]


def _tpl_out(t: Any) -> TemplateOut:
    return t


# ---------- 企业共享模板库 ----------


@router.get("/enterprises/{enterprise_id}/templates", response_model=TemplateListOut)
def list_templates(
    enterprise_id: str,
    session: SessionDep,
    agency: str | None = Query(None, description="按代理机构过滤（模糊）"),
    doc_type: str | None = Query(None, description="按文件类型过滤"),
    name: str | None = Query(None, description="按模板名称过滤（模糊）"),
) -> TemplateListOut:
    items = svc.list_templates(session, enterprise_id, agency=agency, doc_type=doc_type, name=name)
    return TemplateListOut(items=items, total=len(items))


@router.get("/enterprises/{enterprise_id}/templates/{template_id}", response_model=TemplateOut)
def get_template(
    enterprise_id: str,
    template_id: str,
    session: SessionDep,
) -> TemplateOut:
    try:
        return svc.get_template(session, enterprise_id, template_id)
    except NotFoundError:
        raise HTTPException(404, "模板不存在") from None


@router.post(
    "/enterprises/{enterprise_id}/templates/from_path",
    response_model=TemplateOut,
    status_code=201,
)
def create_template_from_path(
    enterprise_id: str,
    body: TemplateCreateIn,
    session: SessionDep,
) -> TemplateOut:
    """收件箱上传（IPC 同机：本地路径直接归档，不经过 multipart）。"""
    try:
        return svc.create_template(session, enterprise_id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/enterprises/{enterprise_id}/templates/{template_id}", response_model=TemplateOut)
def update_template(
    enterprise_id: str,
    template_id: str,
    body: TemplateUpdateIn,
    session: SessionDep,
) -> TemplateOut:
    try:
        return svc.update_template_meta(
            session,
            enterprise_id,
            template_id,
            agency=body.agency,
            doc_type=body.doc_type,
            name=body.name,
            image_max_width_cm=body.image_max_width_cm,
            image_max_height_cm=body.image_max_height_cm,
            note=body.note,
        )
    except NotFoundError:
        raise HTTPException(404, "模板不存在") from None


@router.delete(
    "/enterprises/{enterprise_id}/templates/{template_id}",
    response_model=TemplateDeleteOut,
)
def delete_template(
    enterprise_id: str,
    template_id: str,
    session: SessionDep,
) -> TemplateDeleteOut:
    try:
        svc.soft_delete_template(session, enterprise_id, template_id)
    except NotFoundError:
        raise HTTPException(404, "模板不存在") from None
    return TemplateDeleteOut(deleted=template_id)


@router.post(
    "/enterprises/{enterprise_id}/templates/{template_id}/new-version",
    response_model=TemplateOut,
    status_code=201,
)
def new_version(
    enterprise_id: str,
    template_id: str,
    body: TemplateNewVersionIn,
    session: SessionDep,
) -> TemplateOut:
    try:
        return svc.new_version(session, enterprise_id, template_id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/enterprises/{enterprise_id}/templates/{template_id}/overwrite",
    response_model=TemplateOut,
)
def overwrite_latest(
    enterprise_id: str,
    template_id: str,
    body: TemplateNewVersionIn,
    session: SessionDep,
) -> TemplateOut:
    """覆盖当前最新版本（仅当未被标书引用时可用）。"""
    try:
        return svc.overwrite_latest(session, enterprise_id, template_id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post(
    "/enterprises/{enterprise_id}/templates/{template_id}/compliance",
    response_model=ComplianceResult,
)
def check_compliance(
    enterprise_id: str,
    template_id: str,
    body: TemplateNewVersionIn,
    session: SessionDep,
) -> ComplianceResult:
    """对文件集做合规检查（不保存），返回问题列表。"""
    try:
        tpl = svc.get_template(session, enterprise_id, template_id)
        if tpl.meta.get("chapters"):
            # 用已有章节 + 新文件做一致性检查
            pass
        result = svc.generate_compliance_check(session, enterprise_id, body.file_paths)
        return result
    except NotFoundError:
        raise HTTPException(404, "模板不存在") from None


@router.post(
    "/enterprises/{enterprise_id}/templates/dict-register",
    response_model=dict[str, Any],
)
def register_placeholders(
    enterprise_id: str,
    body: dict[str, Any],
    session: SessionDep,
) -> dict[str, Any]:
    """一键将占位符注册入动态词典。"""
    placeholders: list[str] = body.get("placeholders", [])
    added = svc.register_placeholders_to_dict(enterprise_id, placeholders)
    return {"added": added}


@router.get(
    "/enterprises/{enterprise_id}/templates/check-external-write",
    response_model=dict[str, Any],
)
def check_external_write(
    enterprise_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """检查模板库中是否有文件被软件外修改（比对磁盘 mtime 与 DB 记录）。"""
    from datetime import UTC, datetime

    from app.parse import paths as path_utils

    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    items = repo.list()
    modified: list[str] = []
    for t in items:
        if t.status != "active" or t.deleted_at is not None:
            continue
        version_dir = path_utils.template_version_dir(
            enterprise_id, t.agency, t.doc_type, t.name, t.version
        )
        meta = json.loads(t.meta_json) if isinstance(t.meta_json, str) else t.meta_json
        for ch in meta.get("chapters", []):
            ch_path = version_dir / ch
            if ch_path.exists():
                mtime = datetime.fromtimestamp(ch_path.stat().st_mtime, tz=UTC)
                # 若模板创建时间早于文件修改时间，说明有外部写入
                if mtime > t.created_at.replace(tzinfo=UTC):
                    modified.append(f"{t.agency}/{t.doc_type}/{t.name}/{ch}")
    return {"modified": modified, "count": len(modified)}
