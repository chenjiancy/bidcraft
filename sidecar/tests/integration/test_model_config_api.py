"""TR-6.1/6.2：模型配置 API + 测试连接 + llm_call_log + DPAPI 不落明文。"""

from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient


def _mock_response(
    content: str = "连接成功",
    tokens_in: int = 10,
    tokens_out: int = 5,
) -> MagicMock:
    """构造 httpx.Response mock（OpenAI 兼容格式）。"""
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    }
    return resp


# ========== TR-6.1: 模型配置 CRUD ==========


def test_get_model_config_empty(db_client: TestClient) -> None:
    """初始状态返回 null 配置。"""
    resp = db_client.get("/api/v1/model-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] is None
    assert data["base_url"] is None
    assert data["model"] is None
    assert "api_key" not in data


def test_update_model_config(db_client: TestClient) -> None:
    """可保存模型配置（不含 API Key）。"""
    resp = db_client.put(
        "/api/v1/model-config",
        json={
            "provider": "openai",
            "base_url": "https://api.openai.com",
            "model": "gpt-4o",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o"
    assert "api_key" not in data

    resp2 = db_client.get("/api/v1/model-config")
    assert resp2.json()["model"] == "gpt-4o"


# ========== TR-6.2: 测试连接 + llm_call_log ==========


def test_test_connection_success_records_log(db_client: TestClient) -> None:
    """测试连接成功 → llm_call_log 有记录。"""
    with patch("app.services.llm.httpx.post", return_value=_mock_response()):
        resp = db_client.post(
            "/api/v1/model-config/test",
            json={
                "provider": "openai",
                "base_url": "https://api.openai.com",
                "model": "gpt-4o",
                "api_key": "sk-test-key-12345",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["model"] == "gpt-4o"
    assert data["response_text"] == "连接成功"
    assert data["tokens_in"] == 10
    assert data["tokens_out"] == 5
    assert "api_key" not in data

    # 验证 llm_call_log 有记录
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.deps import get_engine
    from app.models.llm_call_log import LLMCallLog

    with Session(get_engine()) as session:
        logs = list(session.execute(select(LLMCallLog)).scalars().all())
        assert len(logs) == 1
        assert logs[0].model == "gpt-4o"
        assert logs[0].tokens_in == 10
        assert logs[0].tokens_out == 5


def test_test_connection_failure_records_log(db_client: TestClient) -> None:
    """测试连接失败 → llm_call_log 仍有记录。"""
    with patch(
        "app.services.llm.httpx.post",
        side_effect=httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=MagicMock(),
        ),
    ):
        resp = db_client.post(
            "/api/v1/model-config/test",
            json={
                "provider": "openai",
                "base_url": "https://api.openai.com",
                "model": "gpt-4o",
                "api_key": "sk-invalid",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"] is not None

    # 验证 llm_call_log 有记录
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.deps import get_engine
    from app.models.llm_call_log import LLMCallLog

    with Session(get_engine()) as session:
        logs = list(session.execute(select(LLMCallLog)).scalars().all())
        assert len(logs) == 1
        assert logs[0].model == "gpt-4o"


# ========== NFR-3: 首次外联确认 ==========


def test_external_confirmed_default_false(db_client: TestClient) -> None:
    """初始状态外联未确认。"""
    resp = db_client.get("/api/v1/model-config/external-confirmed")
    assert resp.json()["confirmed"] is False


def test_confirm_external(db_client: TestClient) -> None:
    """确认后状态变为 true。"""
    db_client.post("/api/v1/model-config/external-confirmed")
    resp = db_client.get("/api/v1/model-config/external-confirmed")
    assert resp.json()["confirmed"] is True


# ========== DPAPI 不落明文验证 ==========


def test_api_key_not_in_config_kv(db_client: TestClient) -> None:
    """API Key 不落 config_kv。"""
    with patch("app.services.llm.httpx.post", return_value=_mock_response()):
        db_client.post(
            "/api/v1/model-config/test",
            json={
                "provider": "openai",
                "base_url": "https://api.openai.com",
                "model": "gpt-4o",
                "api_key": "sk-secret-key-67890",
            },
        )

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.deps import get_engine
    from app.models.config_kv import ConfigKV

    with Session(get_engine()) as session:
        all_configs = list(session.execute(select(ConfigKV)).scalars().all())
        for cfg in all_configs:
            assert "api_key" not in cfg.key.lower()
            assert "sk-secret" not in (cfg.value or "")
