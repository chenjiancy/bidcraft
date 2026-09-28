"""回收站仓储：记录软删除项、列表、恢复、物理清除。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recycle_bin import RecycleBin


class RecycleBinRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        item_type: str,
        ref_id: str,
        enterprise_id: str | None = None,
    ) -> RecycleBin:
        instance = RecycleBin(
            item_type=item_type,
            ref_id=ref_id,
            enterprise_id=enterprise_id,
        )
        self.session.add(instance)
        return instance

    def list(self, enterprise_id: str | None = None) -> list[RecycleBin]:
        stmt = select(RecycleBin).order_by(RecycleBin.deleted_at.desc())
        if enterprise_id is not None:
            # 该企业的项目回收项 + 该企业本身的回收项
            stmt = stmt.where(
                (RecycleBin.enterprise_id == enterprise_id)
                | ((RecycleBin.item_type == "enterprise") & (RecycleBin.ref_id == enterprise_id))
            )
        return list(self.session.execute(stmt).scalars().all())

    def get(self, item_id: str) -> RecycleBin:
        instance = self.session.get(RecycleBin, item_id)
        if instance is None:
            raise KeyError(item_id)
        return instance

    def remove(self, item_id: str) -> None:
        instance = self.get(item_id)
        self.session.delete(instance)
