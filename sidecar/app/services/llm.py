"""LLM 网关服务（architecture.md 2.2 / tech-selection.md）。

当前用 httpx 直接调用 OpenAI 兼容 /v1/chat/completions 接口。
后续接入多供应商路由时可替换为 LiteLLM（TS-1），接口保持不变。

安全：API Key 仅在调用时临时传入，不落库、不落日志。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.models.llm_call_log import LLMCallLog


@dataclass
class TestConnectionResult:
    __test__ = False  # 防止 pytest 误收集
    success: bool
    model: str
    response_text: str
    tokens_in: int | None
    tokens_out: int | None
    duration_ms: int
    error: str | None = None


@dataclass
class ChatResult:
    __test__ = False
    success: bool
    content: str
    tokens_in: int | None
    tokens_out: int | None
    cached_tokens: int | None
    error: str | None = None


# ---------- test_connection（已有，供模型配置测试连通性） ----------


def test_connection(
    base_url: str,
    model: str,
    api_key: str,
    session: Session,
    project_id: str | None = None,
) -> TestConnectionResult:
    """测试云端模型连通性，记录 llm_call_log。

    发送一条最小消息（"请回复：连接成功"），返回响应信息。
    """
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "请回复：连接成功"}],
        "max_tokens": 20,
    }

    start = time.monotonic()
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        duration_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        data = resp.json()

        response_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens")
        tokens_out = usage.get("completion_tokens")

        _log_call(session, model, tokens_in, tokens_out, duration_ms, project_id)

        return TestConnectionResult(
            success=True,
            model=model,
            response_text=response_text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        error_msg = str(exc)
        _log_call(session, model, None, None, duration_ms, project_id, error=error_msg)
        return TestConnectionResult(
            success=False,
            model=model,
            response_text="",
            tokens_in=None,
            tokens_out=None,
            duration_ms=duration_ms,
            error=error_msg,
        )


# ---------- chat_completion（Task 10，供解析校验模式调用） ----------


def chat_completion(
    base_url: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    session: Session,
    project_id: str | None = None,
) -> ChatResult:
    """通用 chat completion，同步阻塞（由调用方 asyncio.to_thread 包异步层）。"""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "max_tokens": 2048}

    start = time.monotonic()
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=120.0)
        duration_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens")
        tokens_out = usage.get("completion_tokens")
        cached_tokens: int | None = None
        ptd = usage.get("prompt_tokens_details")
        if isinstance(ptd, dict):
            cached_tokens = ptd.get("cached_tokens")

        _log_call(
            session,
            model,
            tokens_in,
            tokens_out,
            duration_ms,
            project_id,
            cached_tokens=cached_tokens,
        )

        return ChatResult(
            success=True,
            content=content,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens=cached_tokens,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        error_msg = str(exc)
        _log_call(session, model, None, None, duration_ms, project_id, error=error_msg)
        return ChatResult(
            success=False,
            content="",
            tokens_in=None,
            tokens_out=None,
            cached_tokens=None,
            error=error_msg,
        )


# ---------- 日志 ----------


def _log_call(
    session: Session,
    model: str,
    tokens_in: int | None,
    tokens_out: int | None,
    duration_ms: int,
    project_id: str | None,
    error: str | None = None,
    cached_tokens: int | None = None,
) -> None:
    """记录 LLM 调用日志（不含 API Key）。"""
    log = LLMCallLog(
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cached_tokens=cached_tokens,
        duration_ms=duration_ms,
        project_id=project_id,
    )
    session.add(log)
    session.commit()
