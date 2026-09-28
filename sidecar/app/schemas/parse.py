"""招标文件解析 API schemas（Task 8）。"""

from typing import Any

from pydantic import BaseModel, Field


class SourceFileIn(BaseModel):
    """Electron 经文件对话框/拖拽得到的本机源文件（同机 sidecar 复制入库）。"""

    name: str = Field(..., min_length=1, max_length=300)
    path: str = Field(..., min_length=1, max_length=1000)


class RegisterSourcesIn(BaseModel):
    files: list[SourceFileIn] = Field(..., min_length=1, max_length=50)


class ParseStartIn(BaseModel):
    """启动（或断点续跑）解析；当前只支持默认路径，无 LLM 开关（Task 9/10 落地）。"""

    reparse: bool = False  # True：忽略已有 success 项全部重跑（谨慎，清 checkpoint）


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
