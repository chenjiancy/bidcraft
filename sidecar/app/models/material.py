"""素材表（architecture.md 四）：企业共享库 + 项目独享库。

分类：资质 / 人员 / 业绩 / 荣誉 / 财务
归属：enterprise_id（企业共享）、project_id 为空表示共享；非空表示项目独享。
版本：每次编辑 version+1，旧版本不再从库中删除（供历史标书引用）。
OCR：每个素材保留 OCR 文本，供 Task 16 素材查询使用。
FTS5：通过 SQLite FTS5 虚表对名称关键字 + OCR 文本建立检索索引（BP-8）。
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import SoftDeleteMixin, TimestampMixin, new_id

VALID_CATEGORIES = ("qualification", "personnel", "performance", "honor", "finance")


class Material(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "material"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("enterprise.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 项目独享时为项目 id，null 表示企业共享库
    project_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # 素材分类：qualification/personnel/performance/honor/finance
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 用户显示的素材名称（可被重命名）
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 归档后的规范文件名（不含路径）
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    # 文件在磁盘上的绝对路径（归档图片，非原始上传文件）
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    # OCR 识别文本（供 FTS5 检索，人工可修改）
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 有效期截止日，YYYYMMDD 或 "长期"
    valid_until: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 版本号，从 1 开始递增
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 素材状态：active / archived / deleted（deleted=软删进回收站）
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # 是否启用 FTS5 索引
    indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
