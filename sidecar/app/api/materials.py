"""素材库 API（Task 15）。

路由前缀：/api/v1/enterprises/{enterprise_id}/materials
项目独享素材路由嵌套在 /projects/{project_id}/ 下。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_session
from app.materials.ocr import build_default_ocr
from app.materials.service import ArchivalError, archive_material
from app.models.material import Material
from app.parse import paths as path_utils
from app.repositories.base import NotFoundError, Scope
from app.repositories.material import MaterialRepository
from app.repositories.recycle_bin import RecycleBinRepository
from app.schemas.material import (
    MaterialCreateIn,
    MaterialDeleteOut,
    MaterialListOut,
    MaterialOut,
    MaterialUpdateIn,
)

# M18 修复：上传文件大小限制（10MB）
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])
SessionDep = Annotated[Session, Depends(get_session)]


def _material_out(m: Material) -> MaterialOut:
    return MaterialOut(
        id=m.id,
        enterprise_id=m.enterprise_id,
        project_id=m.project_id,
        category=m.category,
        name=m.name,
        filename=m.filename,
        file_path=m.file_path,
        ocr_text=m.ocr_text,
        valid_until=m.valid_until,
        version=m.version,
        status=m.status,
        created_at=str(m.created_at),
        updated_at=str(m.updated_at),
    )


# ---------- 企业共享素材库 ----------


@router.get("/enterprises/{enterprise_id}/materials", response_model=MaterialListOut)
def list_materials(
    enterprise_id: str,
    session: SessionDep,
    category: str | None = Query(None, description="按分类过滤"),
    keyword: str | None = Query(None, description="关键字模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> MaterialListOut:
    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id))
    items = repo.list(category=category, keyword=keyword, page=page, page_size=page_size)
    total = repo.count(category=category, keyword=keyword)
    return MaterialListOut(items=[_material_out(m) for m in items], total=total)


@router.get("/enterprises/{enterprise_id}/materials/{material_id}", response_model=MaterialOut)
def get_material(enterprise_id: str, material_id: str, session: SessionDep) -> MaterialOut:
    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id))
    try:
        return _material_out(repo.get(material_id))
    except NotFoundError:
        raise HTTPException(404, "素材不存在") from None


@router.post("/enterprises/{enterprise_id}/materials", response_model=MaterialOut, status_code=201)
def create_material(
    enterprise_id: str,
    body: MaterialCreateIn,
    file: UploadFile,
    session: SessionDep,
) -> MaterialOut:
    """收件箱上传并归档（POST multipart/form-data，同时传字段和文件）。"""
    import tempfile
    from pathlib import Path

    # M18 修复：文件大小校验
    file_size = file.size if file.size is not None else 0
    if file_size > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小 {file_size} 超过限制 {_MAX_UPLOAD_BYTES // 1024 // 1024}MB",
        )

    # 写入收件箱临时目录
    with tempfile.NamedTemporaryFile(suffix=file.filename or ".bin", delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)

    try:
        # 初始化收件箱目录
        inbox = path_utils.inbox_dir(enterprise_id)
        inbox.mkdir(parents=True, exist_ok=True)
        inbox_dest = inbox / (tmp_path.name)
        tmp_path.rename(inbox_dest)

        material = archive_material(
            session,
            enterprise_id,
            original_path=inbox_dest,
            category=body.category,
            ocr_backend=build_default_ocr(),
            custom_name=body.name,
            custom_filename=body.filename,
            valid_until=body.valid_until,
            fields=body.fields,
        )
    except ArchivalError as e:
        raise HTTPException(400, str(e)) from e
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    # M10 修复：记录操作日志
    from app.repositories.app_event import AppEventRepository

    AppEventRepository(session, Scope(enterprise_id=enterprise_id)).record(
        "material_create",
        project_id=None,
        payload={"material_id": material.id, "category": body.category},
    )
    session.commit()

    return _material_out(material)


# ---------- 路径直传接口（IPC 场景：侧边栏同一台机器） ----------


class MaterialPathIn(BaseModel):
    """通过本地路径直接归档素材（适用于 IPC 同机场景）。"""

    file_paths: list[str]
    category: str
    name: str | None = None
    filename: str | None = None
    valid_until: str | None = None
    fields: dict[str, str] | None = None


@router.post(
    "/enterprises/{enterprise_id}/materials/from_path",
    response_model=list[MaterialOut],
    status_code=201,
)
def create_material_from_path(
    enterprise_id: str,
    body: MaterialPathIn,
    session: SessionDep,
) -> list[MaterialOut]:
    """从本地路径批量归档素材（不经过 multipart，适合 IPC 转发）。"""
    from pathlib import Path as _Path

    results: list[MaterialOut] = []
    for fp_str in body.file_paths:
        original_path = _Path(fp_str)
        if not original_path.exists():
            raise HTTPException(400, f"文件不存在: {fp_str}")
        try:
            material = archive_material(
                session,
                enterprise_id,
                original_path=original_path,
                category=body.category,
                ocr_backend=build_default_ocr(),
                custom_name=body.name,
                custom_filename=body.filename,
                valid_until=body.valid_until,
                fields=body.fields,
            )
            results.append(_material_out(material))
        except ArchivalError as e:
            raise HTTPException(400, str(e)) from e
    return results


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/materials/from_path",
    response_model=list[MaterialOut],
    status_code=201,
)
def create_project_material_from_path(
    enterprise_id: str,
    project_id: str,
    body: MaterialPathIn,
    session: SessionDep,
) -> list[MaterialOut]:
    """项目独享：从本地路径批量归档素材。"""
    from pathlib import Path as _Path

    results: list[MaterialOut] = []
    for fp_str in body.file_paths:
        original_path = _Path(fp_str)
        if not original_path.exists():
            raise HTTPException(400, f"文件不存在: {fp_str}")
        try:
            material = archive_material(
                session,
                enterprise_id,
                project_id=project_id,
                original_path=original_path,
                category=body.category,
                ocr_backend=build_default_ocr(),
                custom_name=body.name,
                custom_filename=body.filename,
                valid_until=body.valid_until,
                fields=body.fields,
            )
            results.append(_material_out(material))
        except ArchivalError as e:
            raise HTTPException(400, str(e)) from e
    return results


@router.put("/enterprises/{enterprise_id}/materials/{material_id}", response_model=MaterialOut)
def update_material(
    enterprise_id: str,
    material_id: str,
    body: MaterialUpdateIn,
    session: SessionDep,
) -> MaterialOut:
    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id))
    try:
        m = repo.update(
            material_id,
            name=body.name,
            filename=body.filename,
            ocr_text=body.ocr_text,
            valid_until=body.valid_until,
        )
        session.commit()
        # M10 修复：记录操作日志
        from app.repositories.app_event import AppEventRepository

        AppEventRepository(session, Scope(enterprise_id=enterprise_id)).record(
            "material_update",
            project_id=None,
            payload={"material_id": material_id, "changes": body.model_dump(exclude_unset=True)},
        )
        session.commit()
        return _material_out(m)
    except NotFoundError:
        raise HTTPException(404, "素材不存在") from None


@router.delete(
    "/enterprises/{enterprise_id}/materials/{material_id}",
    response_model=MaterialDeleteOut,
)
def delete_material(enterprise_id: str, material_id: str, session: SessionDep) -> MaterialDeleteOut:
    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id))
    try:
        m = repo.get(material_id)
        repo.soft_delete(material_id)
        # M2 修复：同步删除 FTS5 索引
        repo.delete_fts5_index(material_id, path_utils.fts5_db_path(enterprise_id))
        rb = RecycleBinRepository(session).add(
            item_type="material",
            ref_id=material_id,
            enterprise_id=enterprise_id,
        )
        rb.name = m.name
        rb.file_path = m.file_path
        session.commit()
        # M10 修复：记录操作日志
        from app.repositories.app_event import AppEventRepository

        AppEventRepository(session, Scope(enterprise_id=enterprise_id)).record(
            "material_delete", project_id=None, payload={"material_id": material_id, "name": m.name}
        )
        session.commit()
        return MaterialDeleteOut(deleted=material_id)
    except NotFoundError:
        raise HTTPException(404, "素材不存在") from None


# ---------- 项目独享素材库 ----------


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/materials",
    response_model=MaterialListOut,
)
def list_project_materials(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
    category: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> MaterialListOut:
    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id, project_id=project_id))
    items = repo.list(category=category, keyword=keyword, page=page, page_size=page_size)
    total = repo.count(category=category, keyword=keyword)
    return MaterialListOut(items=[_material_out(m) for m in items], total=total)


@router.get(
    "/enterprises/{enterprise_id}/projects/{project_id}/materials/{material_id}",
    response_model=MaterialOut,
)
def get_project_material(
    enterprise_id: str, project_id: str, material_id: str, session: SessionDep
) -> MaterialOut:
    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id, project_id=project_id))
    try:
        return _material_out(repo.get(material_id))
    except NotFoundError:
        raise HTTPException(404, "素材不存在") from None


@router.post(
    "/enterprises/{enterprise_id}/projects/{project_id}/materials",
    response_model=MaterialOut,
    status_code=201,
)
def create_project_material(
    enterprise_id: str,
    project_id: str,
    body: MaterialCreateIn,
    file: UploadFile,
    session: SessionDep,
) -> MaterialOut:
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=file.filename or ".bin", delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)

    try:
        inbox = path_utils.inbox_dir(enterprise_id, project_id)
        inbox.mkdir(parents=True, exist_ok=True)
        inbox_dest = inbox / (tmp_path.name)
        tmp_path.rename(inbox_dest)

        material = archive_material(
            session,
            enterprise_id,
            project_id=project_id,
            original_path=inbox_dest,
            category=body.category,
            ocr_backend=build_default_ocr(),
            custom_name=body.name,
            custom_filename=body.filename,
            valid_until=body.valid_until,
            fields=body.fields,
        )
    except ArchivalError as e:
        raise HTTPException(400, str(e)) from e
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return _material_out(material)
