"""模型配置 Pydantic schemas。

配置项（供应商/base_url/model）存 config_kv（system scope）；
API Key 走 DPAPI（Electron Main 侧），不落 sidecar 数据库。
"""

from pydantic import BaseModel, ConfigDict, Field


class ModelConfigOut(BaseModel):
    """模型配置读取返回（不含 API Key；has_api_key 由前端从 DPAPI 查询）。"""

    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ModelConfigUpdate(BaseModel):
    """模型配置保存（不含 API Key）。"""

    provider: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field(..., min_length=1, max_length=500)
    model: str = Field(..., min_length=1, max_length=100)


class TestConnectionRequest(BaseModel):
    """测试连接请求（API Key 由前端从 DPAPI 取出临时传入）。"""

    provider: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field(..., min_length=1, max_length=500)
    model: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=1, max_length=500)


class TestConnectionResultOut(BaseModel):
    """测试连接结果。"""

    success: bool
    model: str
    response_text: str
    tokens_in: int | None
    tokens_out: int | None
    duration_ms: int
    error: str | None = None


class ExternalConfirmedOut(BaseModel):
    """首次外联确认状态（NFR-3）。"""

    confirmed: bool
