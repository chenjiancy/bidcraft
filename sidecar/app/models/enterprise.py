"""企业表（architecture.md 四）。"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import SoftDeleteMixin, TimestampMixin, new_id


class Enterprise(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "enterprise"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_person: Mapped[str | None] = mapped_column(String(100))
    # FR-1：委托代理人必填（校验在服务/仓储层配合，数据库层保持 not null）
    agent: Mapped[str] = mapped_column(String(100), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    intro: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
