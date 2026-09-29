"""回收站 API（architecture.md 2.2 + Task 21 完整功能）。

支持两类回收站：
1. 系统回收站（/api/v1/recycle-bin/system）：被删除的企业列表，跨企业可见
2. 企业内回收站（/api/v1/recycle-bin?enterprise_id=xxx）：项目/素材/模板

操作：
- 恢复（POST /recycle-bin/{id}/restore）
- 彻底删除（DELETE /recycle-bin/{id}）：物理删除文件 + 记录
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_session
from app.repositories.recycle_bin import RecycleBinRepository
from app.schemas.enterprise import RecycleBinItemOut

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/recycle-bin", response_model=list[RecycleBinItemOut])
def list_recycle_bin(
    enterprise_id: str | None = Query(None, description="企业 ID；不传则返回系统回收站"),
    item_type: str | None = Query(
        None, description="按类型筛选：enterprise/project/material/template"
    ),
    session: SessionDep = None,  # type: ignore[assignment]
) -> list:
    """列出回收站条目。

    - 不传 enterprise_id：系统回收站（被删除的企业）
    - 传 enterprise_id：该企业的项目/素材/模板回收项，可按 item_type 筛选
    """
    return RecycleBinRepository(session).list(
        enterprise_id=enterprise_id,
        item_type=item_type,
    )


@router.get("/recycle-bin/system", response_model=list[RecycleBinItemOut])
def list_system_recycle_bin(session: SessionDep) -> list:
    """系统回收站：被删除的企业列表（跨企业可见）。"""
    return RecycleBinRepository(session).list()


@router.post("/recycle-bin/{item_id}/restore")
def restore_item(
    item_id: str,
    enterprise_id: str = Query(None, description="企业 ID"),
    session: SessionDep = None,  # type: ignore[assignment]
) -> dict[str, object]:
    bin_repo = RecycleBinRepository(session)
    try:
        bin_repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="回收站项不存在") from None

    _, result = bin_repo.restore(item_id)
    if not result.get("restored"):
        raise HTTPException(status_code=400, detail=result.get("error", "恢复失败")) from None
    # M10 修复：记录操作日志
    from app.repositories.app_event import AppEventRepository
    from app.repositories.base import Scope

    eid = result.get("enterprise_id") or enterprise_id
    if eid:
        AppEventRepository(session, Scope(enterprise_id=str(eid))).record(
            "recycle_bin_restore",
            project_id=None,
            payload={"item_id": item_id, "item_type": result.get("item_type")},
        )
        session.commit()
    return result


@router.delete("/recycle-bin/{item_id}", status_code=204)
def purge_item(item_id: str, session: SessionDep) -> None:
    bin_repo = RecycleBinRepository(session)
    try:
        bin_repo.get(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="回收站项不存在") from None

    result = bin_repo.purge(item_id)
    if not result.get("purged"):
        raise HTTPException(status_code=500, detail=result.get("error", "清理失败")) from None
