"""项目级解析配置（Task 9，FR-2 第 2 点）：一项目一行，payload 为 JSON。

未建配置行的项目在读取时回退默认配置（8 关键项勾选 / 其他不选 / LLM 关）。
项目删除时配置级联清除。
"""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, new_id


class ParseProjectConfig(Base, TimestampMixin):
    __tablename__ = "parse_project_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # ParseConfig 的 JSON 序列化（version/items/llm_enabled/llm_mode）
    payload: Mapped[str] = mapped_column(Text, nullable=False)
