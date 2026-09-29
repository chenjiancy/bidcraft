"""模板表（architecture.md 四）：企业级模板库管理（Task 17）。

目录布局::

    <data_root>/enterprises/<eid>/templates/<agency>/<doc_type>/<name>/v1.0/
    <data_root>/enterprises/<eid>/templates/<agency>/<doc_type>/<name>/v1.1/
    ...

每条记录 = 一个特定版本的模板文件集。
同 (enterprise_id, agency, doc_type, name) 下可有多个版本。
已被任何标书引用过的版本禁止覆盖，只能新建版本。
"""

import json
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import SoftDeleteMixin, TimestampMixin, new_id

VALID_DOC_TYPES = ("bid", "procurement", "quotation")


class Template(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "template"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    enterprise_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("enterprise.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 代理机构名称
    agency: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # 文件类型：bid（招标）/ procurement（采购）/ quotation（询比价）
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 模板名称（同一 agency+doc_type+name 标识一组模板文件集）
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 版本号（从 1 开始递增）
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 磁盘路径（相对于 enterprise 根目录，如 "templates/xx/bid/yy/v1.0"）
    path: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON 元数据：chapters（文件名列表）、图片约束、note、change_note
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # active / deprecated
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # 是否已被标书引用（引用后禁止覆盖当前版本）
    referenced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    @property
    def meta(self) -> dict[str, Any]:
        try:
            return json.loads(self.meta_json) if self.meta_json else {}
        except Exception:
            return {}
