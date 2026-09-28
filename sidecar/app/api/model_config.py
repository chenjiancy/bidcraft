"""模型配置 API（architecture.md 2.2 / NFR-3）。

配置项（供应商/base_url/model）存 config_kv（system scope）；
API Key 走 DPAPI（Electron Main 侧），不落 sidecar 数据库。
测试连接时 API Key 由前端从 DPAPI 取出临时传入，sidecar 用后不存。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_session
from app.repositories.config_kv import ConfigKVRepository
from app.schemas.model_config import (
    ExternalConfirmedOut,
    ModelConfigOut,
    ModelConfigUpdate,
    TestConnectionRequest,
    TestConnectionResultOut,
)
from app.services.llm import test_connection

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])

SessionDep = Annotated[Session, Depends(get_session)]

# config_kv keys
KEY_PROVIDER = "llm.provider"
KEY_BASE_URL = "llm.base_url"
KEY_MODEL = "llm.model"
KEY_EXTERNAL_CONFIRMED = "system.external_confirmed"


@router.get("/model-config", response_model=ModelConfigOut)
def get_model_config(session: SessionDep) -> ModelConfigOut:
    """读取模型配置（不含 API Key）。"""
    repo = ConfigKVRepository(session)
    return ModelConfigOut(
        provider=repo.get_value("system", KEY_PROVIDER),
        base_url=repo.get_value("system", KEY_BASE_URL),
        model=repo.get_value("system", KEY_MODEL),
    )


@router.put("/model-config", response_model=ModelConfigOut)
def update_model_config(body: ModelConfigUpdate, session: SessionDep) -> ModelConfigOut:
    """保存模型配置（不含 API Key）。"""
    repo = ConfigKVRepository(session)
    repo.set_value("system", KEY_PROVIDER, body.provider)
    repo.set_value("system", KEY_BASE_URL, body.base_url)
    repo.set_value("system", KEY_MODEL, body.model)
    session.commit()
    return ModelConfigOut(
        provider=body.provider,
        base_url=body.base_url,
        model=body.model,
    )


@router.post("/model-config/test", response_model=TestConnectionResultOut)
def test_model_connection(
    body: TestConnectionRequest,
    session: SessionDep,
) -> TestConnectionResultOut:
    """测试云端模型连通性，记录 llm_call_log。

    API Key 由前端从 DPAPI 取出临时传入，不落库、不落日志。
    """
    result = test_connection(
        base_url=body.base_url,
        model=body.model,
        api_key=body.api_key,
        session=session,
    )
    return TestConnectionResultOut(
        success=result.success,
        model=result.model,
        response_text=result.response_text,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        duration_ms=result.duration_ms,
        error=result.error,
    )


@router.get("/model-config/external-confirmed", response_model=ExternalConfirmedOut)
def get_external_confirmed(session: SessionDep) -> ExternalConfirmedOut:
    """查询首次外联确认状态（NFR-3）。"""
    repo = ConfigKVRepository(session)
    confirmed = repo.get_value("system", KEY_EXTERNAL_CONFIRMED) == "true"
    return ExternalConfirmedOut(confirmed=confirmed)


@router.post("/model-config/external-confirmed", response_model=ExternalConfirmedOut)
def confirm_external(session: SessionDep) -> ExternalConfirmedOut:
    """标记用户已确认首次外联提示（NFR-3）。"""
    repo = ConfigKVRepository(session)
    repo.set_value("system", KEY_EXTERNAL_CONFIRMED, "true")
    session.commit()
    return ExternalConfirmedOut(confirmed=True)
