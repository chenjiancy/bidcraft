"""config_kv：system / enterprise 两级键值配置。"""

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import new_id


class ConfigKV(Base):
    __tablename__ = "config_kv"
    __table_args__ = (
        UniqueConstraint("scope", "enterprise_id", "key", name="uq_config_kv_scope_ent_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # system|enterprise
    enterprise_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("enterprise.id", ondelete="CASCADE"),
        nullable=True,
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
