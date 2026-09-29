"""模板比对记录（Task 18）。

每个项目在一次模板匹配流程中对应一条 TemplateCompare 记录：
- matched_template_id：命中的企业模板 ID（手动指定时为 None）
- match_method：auto / manual
- similarity_score：自动匹配时的综合得分（0-100），手动时为 null
- findings_json：比对发现 diff 列表，结构见 FindingOut
- association_json：parsed/ 条目 ↔ template-work/ 章节的关联表
- status：matched / review / ready
- rejected_count / accepted_count：差异裁决统计
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import SoftDeleteMixin, TimestampMixin, new_id


class TemplateCompare(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "template_compare"

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
    # 命中的模板 ID；手动指定时为 None
    matched_template_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # auto / manual
    match_method: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    # 自动匹配的相似度得分（0-100），手动指定时为 None
    similarity_score: Mapped[float | None] = mapped_column(Integer, nullable=True)
    # 已复制到的项目 template-work/ 目录路径（相对 data_root）
    work_dir: Mapped[str] = mapped_column(Text, nullable=False)
    # 关联表：{parsed_chapter_key: {template_chapter_name, seq, matched}}
    association_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 差异发现列表（FindingOut 数组）
    findings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 比对状态：matched / review / ready
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="matched")
    # 裁决统计
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 全部裁决完成时间
    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # 机械检查前置结果（bp4_summary_json）
    bp4_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
