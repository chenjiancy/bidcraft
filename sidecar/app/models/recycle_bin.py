"""回收站表（architecture.md 四）：软删除中转站，30 天可配清除。

Task 5 实现"进回收站 + 恢复"；Task 21 完善为完整回收站：
- 支持企业/项目/素材/模板四类
- 素材/模板恢复后回到原目录
- 保留时长可配（config_kv），默认 30 天
- 定时清理到期条目（物理删文件 + 删记录）
- 系统回收站（跨企业列示被删企业）
- 恢复冲突处理（改名恢复，不覆盖）
- 所有操作写 app_event 留痕
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import new_id

PURGE_AFTER_DAYS = 30


def _default_purge_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=PURGE_AFTER_DAYS)


class RecycleBin(Base):
    __tablename__ = "recycle_bin"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # 类型：enterprise|project|material|template
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enterprise_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("enterprise.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ref_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # 条目显示名称（素材/模板/企业/项目的名称）
    name: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    # 恢复状态：soft_deleted | restoring | conflict
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="soft_deleted")
    # 原名称（冲突时用：rename_to_{original_name}）
    original_name: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    # 素材文件路径（用于物理清理时删除）
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purge_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_default_purge_at
    )
