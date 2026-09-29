"""素材提取清单条目（Task 16）。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import SoftDeleteMixin, TimestampMixin, new_id


class MaterialExtractItem(Base, TimestampMixin, SoftDeleteMixin):
    """待查素材需求项：从评分办法/资格条款聚合，经多轮查询匹配后选定。

    round 表示当前轮次；status ∈ pending / selected / missing / deferred。
    """

    __tablename__ = "material_extract_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("enterprise.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requirement_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="score_table")
    source_anchor: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_material_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
