"""渲染 API schemas（Task 19）。"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------- 渲染计划 ----------


class PlaceholderInfoOut(BaseModel):
    """渲染计划中单条占位符描述。"""

    name: str
    type: str  # a_class / b_class / image
    description: str = ""
    value: str | None = None
    needs_manual: bool = False
    is_missing: bool = False


class RenderPlanItemOut(BaseModel):
    """渲染计划中单章节条目。"""

    chapter: str
    seq: int
    template_path: str
    placeholders: list[PlaceholderInfoOut] = Field(default_factory=list)
    missing_count: int = 0


class RenderPlanOut(BaseModel):
    """GET /render/plan 响应。"""

    plan: list[RenderPlanItemOut]
    total: int
    missing_total: int


# ---------- 渲染确认 ----------


class BClassAdjustmentIn(BaseModel):
    """B 类占位符人工取值调整。"""

    placeholder: str = Field(..., max_length=200)
    value: str = Field(..., max_length=1000)


class ConfirmRenderPlanIn(BaseModel):
    """POST /render/confirm 请求体。"""

    b_class_adjustments: list[BClassAdjustmentIn] = Field(default_factory=list, max_length=50)
    note: str | None = Field(default=None, max_length=500)


class ConfirmRenderPlanOut(BaseModel):
    """POST /render/confirm 响应。"""

    status: str  # READY_TO_RENDER
    total_placeholders: int
    b_class_needs_manual: int
    missing_count: int


# ---------- 渲染启动（SSE） ----------


class RenderStartIn(BaseModel):
    """POST /render/start 请求体。"""

    re_render: bool = False  # True：忽略已有 success 项全部重跑


# ---------- 警告清单 ----------


class WarningItemOut(BaseModel):
    """渲染后缺失/问题占位警告。"""

    chapter: str
    placeholder: str
    problem_type: Literal["missing_text", "missing_image", "b_class_uncertain"]
    suggestion: str


class WarningListOut(BaseModel):
    """GET /render/warnings 响应。"""

    warnings: list[WarningItemOut]
    total: int
    missing_text: int
    missing_image: int
    b_class_uncertain: int


# ---------- 一致性审计 ----------


class TermIssueOut(BaseModel):
    chapter: str
    term: str
    count: int
    expected: str


class ConsistencyIssueOut(BaseModel):
    field: str
    description: str
    chapters: dict[str, str]
    problem: str


class AuditResultOut(BaseModel):
    """GET /render/audit 响应。"""

    doc_type: str
    term_issues: list[TermIssueOut]
    consistency_issues: list[ConsistencyIssueOut]
    summary: str


# ---------- 渲染状态 ----------


class RenderStatusOut(BaseModel):
    """GET /render/status 响应。"""

    parse_status: str
    rendering: bool = False
    current_chapter: str | None = None
    completed_chapters: list[str] = Field(default_factory=list)
    total_chapters: int = 0
    error_msg: str | None = None


# ---------- PDF 导出（Task 20） ----------


class ExportStatusOut(BaseModel):
    """GET /render/export/status 响应。"""

    export_status: str  # "idle" | "exporting" | "completed" | "cancelled" | "error"
    merged_path: str | None = None
    total_chapters: int = 0
    current_chapter: str | None = None
    error_msg: str | None = None
