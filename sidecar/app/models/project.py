"""项目表（architecture.md 四）：核心隔离边界。"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import SoftDeleteMixin, TimestampMixin, new_id


class Project(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100))
    # FR-1：项目委托代理人选填（缺省取企业代理人）
    agent: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # EM-5 解析阶段状态机（Task 8）：INIT/UPLOADED/PARSING/PARSED（后续 Task 扩展）
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="INIT")
