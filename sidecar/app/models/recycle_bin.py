"""回收站表（architecture.md 四）：软删除中转站，30 天可配清除。

Task 5 仅实现"进回收站 + 恢复 + 物理清除"；30 天定时清理在 1.2 收尾。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import new_id

PURGE_AFTER_DAYS = 30


def _default_purge_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=PURGE_AFTER_DAYS)


class RecycleBin(Base):
    __tablename__ = "recycle_bin"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)  # enterprise|project
    enterprise_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("enterprise.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ref_id: Mapped[str] = mapped_column(String(32), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purge_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_default_purge_at
    )
