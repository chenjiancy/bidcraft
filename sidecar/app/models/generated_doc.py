"""逐章渲染产物记录（Task 19）。

每个章节渲染后生成一条 GeneratedDoc 记录：
- chapter：章节名（与格式清单对齐）
- seq：序号（与格式清单 seq 编号一致，用于 output/ 命名和 Task 20 合并顺序）
- file_path：渲染产物 Word 文件路径（相对于项目根）
- source_template_version：渲染时绑定的模板版本快照
- status：pending / rendering / success / error
- error_msg：渲染失败时的错误信息
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, new_id


class GeneratedDoc(Base, TimestampMixin):
    __tablename__ = "generated_doc"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("enterprise.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 章节名
    chapter: Mapped[str] = mapped_column(String(255), nullable=False)
    # 序号（格式清单 seq，用于命名和合并顺序）
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # 渲染产物 Word 文件路径（相对于项目根，如 output/01_投标函.docx）
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 渲染时绑定的模板版本快照
    source_template_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 渲染状态：pending / rendering / success / error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # 渲染失败时的错误信息
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 渲染完成时间
    rendered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
