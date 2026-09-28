"""LLM 校验模式单测（TR-10.6/10.7/10.8）：幻觉拦截 / 审计 / 预热顺序。"""

from typing import Any

import pytest

from app.parse import llm_validate
from app.services.llm import ChatResult


class _FakeSession:
    """最小 session 替身：chat_completion 只调用 add/commit。"""

    def __init__(self) -> None:
        self.logs: list[Any] = []

    def add(self, obj: Any) -> None:
        self.logs.append(obj)

    def commit(self) -> None:
        pass

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *_a: Any) -> None:
        pass


@pytest.fixture
def fake_session() -> _FakeSession:
    return _FakeSession()


@pytest.fixture
def factory(fake_session: _FakeSession):
    def _factory() -> _FakeSession:
        return fake_session

    return _factory


def _ok(content: str, cached: int | None = None) -> ChatResult:
    return ChatResult(
        success=True, content=content, tokens_in=100, tokens_out=20, cached_tokens=cached
    )


def test_validate_item_ok_and_anchor_verified(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    """TR-10.6：quote 能在原文找到 → anchor_verified=True。"""
    calls: list[list[dict[str, str]]] = []

    def fake_chat(base_url, model, api_key, messages, session, project_id=None):
        calls.append(messages)
        return _ok(
            '{"is_hard_constraint":true,"constraint":"不超过50页",'
            '"quote":"不超过50页","risk":"low"}'
        )

    monkeypatch.setattr(llm_validate, "chat_completion", fake_chat)
    out = llm_validate.validate_item(
        "page_limit",
        "页数上限",
        "全文：监理大纲不超过50页。",
        "监理大纲不超过50页",
        "http://x",
        "m",
        "k",
        factory,
        "p1",
    )
    assert out["status"] == "ok"
    assert out["anchor_verified"] is True
    assert out["data"]["is_hard_constraint"] is True


def test_validate_item_hallucinated_quote_marked_high(
    monkeypatch: pytest.MonkeyPatch, factory
) -> None:
    """TR-10.6 幻觉拦截：quote 不在原文 → 强制 risk=high 且清空 quote。"""

    def fake_chat(base_url, model, api_key, messages, session, project_id=None):
        return _ok(
            '{"is_hard_constraint":true,"constraint":"假","quote":"原文不存在的话","risk":"low"}'
        )

    monkeypatch.setattr(llm_validate, "chat_completion", fake_chat)
    out = llm_validate.validate_item(
        "k", "标签", "真实原文", "片段", "http://x", "m", "k", factory, "p1"
    )
    assert out["anchor_verified"] is False
    assert out["data"]["risk"] == "high"
    assert out["data"]["quote"] == ""


def test_validate_item_llm_error(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    def fake_chat(base_url, model, api_key, messages, session, project_id=None):
        return ChatResult(
            success=False,
            content="",
            tokens_in=None,
            tokens_out=None,
            cached_tokens=None,
            error="timeout",
        )

    monkeypatch.setattr(llm_validate, "chat_completion", fake_chat)
    out = llm_validate.validate_item("k", "l", "m", "s", "u", "m", "k", factory, "p1")
    assert out["status"] == "error"
    assert "timeout" in (out["error"] or "")


def test_audit_gap_ok(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    """TR-10.7：审计返回大类数量比对。"""

    def fake_chat(base_url, model, api_key, messages, session, project_id=None):
        return _ok('{"categories_count":{"资格条款":3,"技术要求":5},"gaps":[]}', cached=800)

    monkeypatch.setattr(llm_validate, "chat_completion", fake_chat)
    items = [
        {"category": "资格条款", "selected": True, "status": "found"},
        {"category": "技术要求", "selected": True, "status": "found"},
        {"category": "商务评分", "selected": False, "status": "off"},
    ]
    out = llm_validate.audit_gap("全文", items, "u", "m", "k", factory, "p1")
    assert out["status"] == "ok"
    assert out["data"]["categories_count"]["资格条款"] == 3


def test_cached_tokens_passthrough(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    """TR-10.8：cached_tokens 从 LLM 响应透传（预热/并发的日志顺序由集成测试覆盖）。"""
    captured: list[int | None] = []

    def fake_chat(base_url, model, api_key, messages, session, project_id=None):
        res = _ok(
            '{"is_hard_constraint":false,"constraint":"","quote":"","risk":"low"}',
            cached=500,
        )
        captured.append(res.cached_tokens)
        return res

    monkeypatch.setattr(llm_validate, "chat_completion", fake_chat)
    out = llm_validate.validate_item(
        "project_overview", "项目概述", "全文", "片段", "u", "m", "k", factory, "p1"
    )
    assert out["status"] == "ok"
    assert captured == [500]
