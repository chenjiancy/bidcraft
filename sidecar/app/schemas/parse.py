"""招标文件解析 API schemas（Task 8）。"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceFileIn(BaseModel):
    """Electron 经文件对话框/拖拽得到的本机源文件（同机 sidecar 复制入库）。"""

    name: str = Field(..., min_length=1, max_length=300)
    path: str = Field(..., min_length=1, max_length=1000)


class RegisterSourcesIn(BaseModel):
    files: list[SourceFileIn] = Field(..., min_length=1, max_length=50)


class ParseStartIn(BaseModel):
    """启动（或断点续跑）解析。

    api_key：LLM 校验模式（Task 10）的云端 Key，由前端从 DPAPI 取出临时传入，
    不落库、不落日志；纯规则路径无需传入。
    """

    reparse: bool = False  # True：忽略已有 success 项全部重跑（谨慎，清 checkpoint）
    api_key: str | None = Field(default=None, max_length=200)


class ParseRetryIn(BaseModel):
    """单项重试：item 为 checkpoint item key；为空则整任务续跑（只跑未成功项）。"""

    item: str | None = None


class EngineStatusOut(BaseModel):
    available: bool
    python_path: str | None = None
    version: str | None = None
    cuda_available: bool | None = None
    cuda_device: str | None = None
    error: str | None = None
    libreoffice_available: bool = False


class ParseStatusOut(BaseModel):
    parse_status: str
    running: bool = False
    sources: dict[str, Any] = {}
    checkpoint: dict[str, Any] | None = None
    chapters: dict[str, Any] | None = None
    dedupe: dict[str, Any] | None = None
    # Task 10：extract_list.json 摘要（doc_type/items 统计/red_flags/llm 状态）
    extraction: dict[str, Any] | None = None
    # Task 11：score_table.json 摘要（categories/total_score/合计校验/schema_validated/llm）
    score: dict[str, Any] | None = None
    # Task 12：投标文件格式逐章 docx 摘要（files/cover/completed/errors/red_flags）
    docx: dict[str, Any] | None = None
    # Task 13：已确认清单摘要（confirmed_at/total_items/confirmed_items/all_confirmed）
    confirmed: dict[str, Any] | None = None


# ---------- Task 13：解析清单复核与确认 ----------


class ParseChecklistOut(BaseModel):
    """GET /parse/checklist：返回三类产物的全量 payload 供前端复核。"""

    parse_status: str
    extraction: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    docx: dict[str, Any] | None = None
    confirmed: dict[str, Any] | None = None
    review_state: dict[str, Any] | None = None


class ParseConfirmItem(BaseModel):
    """单条目确认状态（前端回传）。"""

    tab: Literal["extraction", "score", "docx"]
    item_id: str
    confirmed: bool
    override: dict[str, Any] | None = None
    deleted: bool = False


class ParseConfirmIn(BaseModel):
    """POST /parse/confirm 请求体。"""

    items: list[ParseConfirmItem] = Field(..., min_length=1)
    extraction: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    docx: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=500)


class ParseConfirmOut(BaseModel):
    """POST /parse/confirm 响应。"""

    parse_status: str
    confirmed_at: str
    checklist_path: str
    total_items: int
    confirmed_items: int


# ---------- Task 9：解析配置 ----------


class ParseConfigItemOut(BaseModel):
    key: str
    label: str
    required: bool
    selected: bool


class ParseConfigOut(BaseModel):
    # True 表示项目尚未保存过配置，返回的是默认配置
    is_default: bool
    items: list[ParseConfigItemOut]
    llm_enabled: bool
    llm_mode: str


class ParseConfigUpdate(BaseModel):
    """勾选的配置项 key 全集（关键项必须包含）+ LLM 开关与模式。"""

    selected: list[str] = Field(..., max_length=50)
    llm_enabled: bool = False
    llm_mode: str | None = None


class ParseConfigSavedOut(BaseModel):
    config: ParseConfigOut
    # 已完成解析（PARSED）后发生配置变更：要素层需重新解析才生效
    reparse_required: bool = False
    changes: dict[str, Any] = {}
    # 受影响的 checkpoint item key（Task 9 物理层不受影响恒为空；Task 10 扩展）
    affected_items: list[str] = []
