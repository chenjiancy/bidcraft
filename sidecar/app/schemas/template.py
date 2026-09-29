"""模板库 schema（Task 17）。"""

from typing import Any

from pydantic import BaseModel, Field


class TemplateOut(BaseModel):
    """模板记录输出。"""

    id: str
    enterprise_id: str
    agency: str
    doc_type: str
    name: str
    version: int
    path: str
    meta: dict[str, Any]
    status: str
    referenced: bool
    created_at: str
    updated_at: str


class TemplateListOut(BaseModel):
    """模板列表输出。"""

    items: list[TemplateOut]
    total: int


class TemplateCreateIn(BaseModel):
    """从本地路径上传模板文件集。"""

    agency: str = Field(..., min_length=1, max_length=200, description="代理机构名称")
    doc_type: str = Field(..., description="文件类型：bid / procurement / quotation")
    name: str = Field(..., min_length=1, max_length=200, description="模板名称")
    file_paths: list[str] = Field(..., description="本地 docx 文件路径列表（章节文件）")
    # 可选图片约束
    image_max_width_cm: float | None = None
    image_max_height_cm: float | None = None
    note: str = ""


class TemplateNewVersionIn(BaseModel):
    """新建版本入参（必须有变更说明）。"""

    file_paths: list[str] = Field(..., min_length=1, description="新版本的 docx 文件路径列表")
    change_note: str = Field(..., min_length=1, description="变更说明（必填）")
    image_max_width_cm: float | None = None
    image_max_height_cm: float | None = None
    note: str = ""


class TemplateUpdateIn(BaseModel):
    """编辑模板属性（仅编辑 metadata，不修改文件；修改文件须走新建版本）。"""

    agency: str | None = None
    doc_type: str | None = None
    name: str | None = None
    image_max_width_cm: float | None = None
    image_max_height_cm: float | None = None
    note: str | None = None


class PlaceholderIssue(BaseModel):
    """占位符问题（语法错误或未登记词典）。"""

    placeholder: str
    kind: str = "unknown"  # text / image / table_row / conditional / invalid
    registered_in_dict: bool = False


class ComplianceIssue(BaseModel):
    """合规检查问题。"""

    code: str  # STRUCT / PLACEHOLDER / CHAPTER_MISMATCH
    message: str
    file: str | None = None


class ComplianceResult(BaseModel):
    """合规检查结果。"""

    ok: bool
    issues: list[ComplianceIssue]
    placeholders: list[PlaceholderIssue] = []


class TemplateDeleteOut(BaseModel):
    deleted: str


class DictionaryCheckResult(BaseModel):
    """占位符词典检查结果。"""

    unregistered: list[str]
    all_registered: bool
