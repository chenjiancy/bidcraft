"""回收站 API（architecture.md 2.2）。

恢复：清除软删除标记 + 删除回收站记录。
物理清除：仅删除回收站记录（原数据已软删，不做额外清理）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_session
from app.repositories.base import NotFoundError, Scope
from app.repositories.enterprise import EnterpriseRepository
from app.repositories.project import ProjectRepository
from app.repositories.recycle_bin import RecycleBinRepository
from app.schemas.enterprise import RecycleBinItemOut

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/recycle-bin", response_model=list[RecycleBinItemOut])
def list_recycle_bin(
    session: SessionDep,
    enterprise_id: str | None = None,
) -> list:
    return RecycleBinRepository(session).list(enterprise_id=enterprise_id)


@router.post("/recycle-bin/{item_id}/restore")
def restore_item(item_id: str, session: SessionDep) -> dict[str, str]:
    bin_repo = RecycleBinRepository(session)
    try:
        item = bin_repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="回收站项不存在") from None

    if item.item_type == "enterprise":
        ent_repo = EnterpriseRepository(session)
        try:
            ent = ent_repo.get(item.ref_id, include_deleted=True)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="原企业已不存在") from None
        ent.deleted_at = None
    elif item.item_type == "project":
        if not item.enterprise_id:
            raise HTTPException(status_code=400, detail="回收站项缺少企业归属") from None
        ent_repo = EnterpriseRepository(session)
        try:
            ent_repo.get(item.enterprise_id)
        except NotFoundError:
            raise HTTPException(status_code=400, detail="原企业已不存在") from None
        repo = ProjectRepository(session, Scope(enterprise_id=item.enterprise_id))
        try:
            project = repo.get(item.ref_id, include_deleted=True)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="原项目已不存在") from None
        project.deleted_at = None
    else:
        raise HTTPException(status_code=400, detail=f"未知类型: {item.item_type}") from None

    result = {"restored": "true", "item_type": item.item_type, "ref_id": item.ref_id}
    bin_repo.remove(item_id)
    session.commit()
    return result


@router.delete("/recycle-bin/{item_id}", status_code=204)
def purge_item(item_id: str, session: SessionDep) -> None:
    bin_repo = RecycleBinRepository(session)
    try:
        bin_repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="回收站项不存在") from None
    bin_repo.remove(item_id)
    session.commit()
