"""Task 10 要素提取集成测试（TR-10.1~10.9）。

MinerU 以 fake 替换（中文标题块供章节切分与规则粗分）；
LLM 校验模式 monkeypatch llm_validate.chat_completion，断言预热顺序与产物；
chat_completion 的 llm_call_log 记录用 fake httpx 验证（cached_tokens）。
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.deps import get_engine
from app.db.session import session_factory
from app.models.llm_call_log import LLMCallLog
from app.parse import llm_validate
from app.parse import service as parse_service
from app.parse.engine import RawResult
from app.services import llm as llm_svc
from app.services.llm import ChatResult
from tests.integration.test_parse_api import FakeMineru, _patch_engine, make_text_pdf


class FakeMineruCN(FakeMineru):
    """中文标题块：封面判型 + 投标人须知/保证金/废标章节供规则粗分匹配。"""

    async def __call__(self, input_file: Path, out_dir: Path, **kw: Any) -> RawResult:
        result = await super().__call__(input_file, out_dir, **kw)
        if input_file.stem in self.fail_stems:
            return result
        base = out_dir / input_file.stem
        stem = input_file.stem
        blocks = [
            {"type": "text", "text": "监理招标文件", "page_idx": 0, "text_level": 1},
            {"type": "text", "text": "投标人应按要求提交投标文件与投标函。", "page_idx": 0},
            {
                "type": "text",
                "text": "第一章 投标人须知",
                "page_idx": 1,
                "text_level": 1,
                "bbox": [10.0, 20.0, 300.0, 60.0],
            },
            {"type": "text", "text": "一、投标保证金", "page_idx": 1, "text_level": 2},
            {
                "type": "text",
                "text": "投标保证金为人民币5万元，投标截止前3日缴纳。",
                "page_idx": 1,
            },
            {"type": "text", "text": "二、废标条款", "page_idx": 2, "text_level": 2},
            {"type": "text", "text": "投标文件页数不得超过80页，否则按废标处理。", "page_idx": 2},
        ]
        cl = base / f"{stem}_content_list.json"
        cl.write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
        md = base / f"{stem}.md"
        md.write_text(
            "# 监理招标文件\n\n第一章 投标人须知\n\n投标保证金为人民币5万元。\n"
            "二、废标条款\n\n投标文件页数不得超过80页。\n",
            encoding="utf-8",
        )
        return RawResult(base, md, cl, None, None, [])


@pytest.fixture
def project(db_client: TestClient) -> tuple[str, str]:
    ent = db_client.post("/api/v1/enterprises", json={"name": "测试企业", "agent": "张三"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "测试项目"}
    ).json()
    return ent["id"], proj["id"]


def _register_and_parse(
    db_client: TestClient,
    eid: str,
    pid: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str | None = None,
    selected_keys: set[str] | None = None,
    configure: bool = True,
) -> list[dict[str, Any]]:
    from app.parse.config import REQUIRED_KEYS

    pdf = tmp_path / "监理招标文件.pdf"
    make_text_pdf(pdf, ["tender doc " * 20])
    db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/sources",
        json={"files": [{"name": "监理招标文件.pdf", "path": str(pdf)}]},
    )
    if configure:
        # 默认只勾选关键项；test_extract_coarse_pipeline 需要 bid_bond 勾选
        cfg = db_client.put(
            f"/api/v1/enterprises/{eid}/projects/{pid}/parse/config",
            json={
                "selected": sorted(selected_keys if selected_keys else REQUIRED_KEYS),
                "llm_enabled": False,
                "llm_mode": None,
            },
        )
        assert cfg.status_code == 200, cfg.text
    _patch_engine(monkeypatch, FakeMineruCN(), {})
    events: list[dict[str, Any]] = []
    body: dict[str, Any] = {"reparse": False}
    if api_key:
        body["api_key"] = api_key
    with db_client.stream(
        "POST", f"/api/v1/enterprises/{eid}/projects/{pid}/parse/start", json=body
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _set_llm_config(db_client: TestClient, eid: str, pid: str, mode: str) -> None:
    from app.parse.config import REQUIRED_KEYS

    resp = db_client.put(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/config",
        json={
            "selected": sorted(REQUIRED_KEYS),
            "llm_enabled": True,
            "llm_mode": mode,
        },
    )
    assert resp.status_code == 200, resp.text


def _set_model_config(db_client: TestClient) -> None:
    resp = db_client.put(
        "/api/v1/model-config",
        json={"provider": "openai", "base_url": "http://fake-llm", "model": "fake-model"},
    )
    assert resp.status_code == 200, resp.text


# ---------- 规则粗分（TR-10.1/10.2/10.4/10.5） ----------


def test_extract_coarse_pipeline(
    db_client: TestClient, project: tuple[str, str], tmp_path: Path, monkeypatch
) -> None:
    eid, pid = project
    from app.parse.config import REQUIRED_KEYS

    events = _register_and_parse(
        db_client,
        eid,
        pid,
        tmp_path,
        monkeypatch,
        selected_keys=REQUIRED_KEYS | {"bid_bond"},  # bid_bond 为可选项，需显式勾选
    )
    assert events[-1]["stage"] == "completed"

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    items = {i["key"]: i for i in status["checkpoint"]["items"]}
    assert items["extract:coarse"]["state"] == "success"
    assert "extract:llm" not in items  # LLM 默认关闭，不注册

    # extract_list.json 落 structured/，术语判型为招标
    extract_file = parse_service.paths.extract_list_path(eid, pid)
    assert extract_file.is_file()
    payload = json.loads(extract_file.read_text(encoding="utf-8"))
    assert payload["doc_type"]["type"] == "招标"
    assert payload["llm"]["status"] == "not_run"

    bid_bond = next(i for i in payload["items"] if i["key"] == "bid_bond")
    assert bid_bond["status"] == "found"
    assert bid_bond["category"] == "资格条款"
    assert any(c["kind"] == "amount" for c in bid_bond["matches"][0]["constraints"])

    invalid = next(i for i in payload["items"] if i["key"] == "invalid_bid")
    assert invalid["status"] == "found"
    assert invalid["category"] == "废标条款"
    assert any(
        c["kind"] == "page_limit" and c["value"] == "80页"
        for c in invalid["matches"][0]["constraints"]
    )

    # 状态摘要
    assert status["extraction"]["doc_type"] == "招标"
    assert status["extraction"]["items_total"] == 9  # 8 关键项 + bid_bond
    assert status["extraction"]["items_extracted"] >= 2

    # 术语动态词典已累积
    dict_path = parse_service.paths.data_root() / "config" / "keywords.dict.json"
    assert dict_path.is_file()
    kd = json.loads(dict_path.read_text(encoding="utf-8"))
    assert kd["history"][0]["doc_type"] == "招标"


# ---------- TR-10.9：双通道不调 LLM ----------


def test_dual_channel_defers_and_never_calls_llm(
    db_client: TestClient, project: tuple[str, str], tmp_path: Path, monkeypatch
) -> None:
    eid, pid = project
    _set_llm_config(db_client, eid, pid, "dual_channel")

    def _forbidden(*_a: Any, **_kw: Any) -> ChatResult:
        raise AssertionError("dual_channel 模式不得调用 LLM")

    monkeypatch.setattr(llm_validate, "chat_completion", _forbidden)
    events = _register_and_parse(
        db_client, eid, pid, tmp_path, monkeypatch, api_key="sk-x", configure=False
    )
    assert events[-1]["stage"] == "completed"

    payload = json.loads(
        parse_service.paths.extract_list_path(eid, pid).read_text(encoding="utf-8")
    )
    assert payload["llm"]["status"] == "deferred"
    assert "双通道" in payload["llm"]["note"]


# ---------- TR-10.6/10.7/10.8：校验模式 ----------


def test_llm_validate_mode_warmup_then_batch(
    db_client: TestClient, project: tuple[str, str], tmp_path: Path, monkeypatch
) -> None:
    eid, pid = project
    _set_llm_config(db_client, eid, pid, "validate")
    _set_model_config(db_client)
    monkeypatch.setattr(parse_service, "_LLM_CACHE_WARMUP_WAIT", 0)

    calls: list[str] = []

    def fake_chat(base_url, model, api_key, messages, session, project_id=None):
        user = messages[1]["content"]
        label = user.split("\n", 1)[0]
        calls.append(label)
        if "审计" in user or "大类" in user:
            return ChatResult(True, '{"categories_count":{"通用":8},"gaps":[]}', 10, 5, 400)
        return ChatResult(
            True,
            '{"is_hard_constraint":false,"constraint":"","quote":"","risk":"low"}',
            10,
            5,
            400,
        )

    monkeypatch.setattr(llm_validate, "chat_completion", fake_chat)
    events = _register_and_parse(
        db_client, eid, pid, tmp_path, monkeypatch, api_key="sk-x", configure=False
    )
    assert events[-1]["stage"] == "completed"

    # TR-10.8：首调用为项目概述（预热），审计最后
    assert calls[0] == "招标要素：项目概述"
    assert len(calls) == 8 + 1  # 8 勾选项 + 1 审计

    payload = json.loads(
        parse_service.paths.extract_list_path(eid, pid).read_text(encoding="utf-8")
    )
    assert payload["llm"]["status"] == "done"
    assert payload["llm"]["validated"] == 8
    assert payload["llm"]["audit"]["status"] == "ok"
    overview = next(i for i in payload["items"] if i["key"] == "project_overview")
    assert overview["llm"]["status"] == "ok"

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    items = {i["key"]: i for i in status["checkpoint"]["items"]}
    assert items["extract:llm"]["state"] == "success"


def test_llm_validate_missing_api_key_marks_error_but_parsed(
    db_client: TestClient, project: tuple[str, str], tmp_path: Path, monkeypatch
) -> None:
    """LLM 开启但缺 API Key：extract:llm 置 error，整跑仍 PARSED（可选增强）。"""
    eid, pid = project
    _set_llm_config(db_client, eid, pid, "validate")
    _set_model_config(db_client)
    events = _register_and_parse(
        db_client, eid, pid, tmp_path, monkeypatch, configure=False
    )  # 不传 api_key
    assert events[-1]["stage"] == "completed"

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status["parse_status"] == "PARSED"
    items = {i["key"]: i for i in status["checkpoint"]["items"]}
    assert items["extract:coarse"]["state"] == "success"
    assert items["extract:llm"]["state"] == "error"
    assert "API Key" in (items["extract:llm"]["error"] or "")


# ---------- TR-9.4/Task 10：配置变更 → 单项重试 ----------


def test_config_change_affects_extract_items_only(
    db_client: TestClient, project: tuple[str, str], tmp_path: Path, monkeypatch
) -> None:
    eid, pid = project
    _register_and_parse(db_client, eid, pid, tmp_path, monkeypatch)

    from app.parse.config import REQUIRED_KEYS

    resp = db_client.put(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/config",
        json={
            "selected": sorted(REQUIRED_KEYS | {"bid_bond"}),
            "llm_enabled": False,
            "llm_mode": None,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # 物理层不受影响；extract:coarse 在受影响清单（llm 未启用故无 extract:llm）
    assert data["affected_items"] == ["extract:coarse"]
    assert data["reparse_required"] is True

    # 单项重试 extract:coarse → 级联清 extract_list.json，续跑后重建
    retry = db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/retry",
        json={"item": "extract:coarse"},
    )
    assert retry.status_code == 200
    assert not parse_service.paths.extract_list_path(eid, pid).is_file()

    fake = FakeMineruCN()
    _patch_engine(monkeypatch, fake, {})
    events: list[dict[str, Any]] = []
    with db_client.stream(
        "POST", f"/api/v1/enterprises/{eid}/projects/{pid}/parse/start", json={}
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert events[-1]["stage"] == "completed"
    # 物理层未重跑（MinerU 无新调用），仅要素层重建
    assert fake.calls == []
    assert parse_service.paths.extract_list_path(eid, pid).is_file()


# ---------- chat_completion 日志（cached_tokens，TR-10.8 证据） ----------


def test_chat_completion_logs_cached_tokens(db_client: TestClient, monkeypatch) -> None:
    import httpx

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "prompt_tokens_details": {"cached_tokens": 88},
                },
            }

    def fake_post(url: str, **kw: Any) -> _Resp:
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    factory = session_factory(get_engine())
    with factory() as session:
        result = llm_svc.chat_completion(
            "http://fake", "m", "sk-x", [{"role": "user", "content": "hi"}], session
        )
    assert result.success and result.cached_tokens == 88

    with factory() as session:
        row = session.query(LLMCallLog).order_by(LLMCallLog.created_at.desc()).first()
    assert row is not None and row.cached_tokens == 88 and row.tokens_in == 100


# 防止 asyncio 未用告警（本文件异步路径由 service 内部驱动）
_ = asyncio
