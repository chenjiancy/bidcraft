"""Task 13 解析清单复核与确认集成测试。"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.parse import paths
from tests.integration.test_parse_api import _patch_engine, make_text_pdf
from tests.integration.test_parse_docx_api import FakeMineruFormat


@pytest.fixture
def project(db_client: TestClient) -> tuple[str, str]:
    ent = db_client.post("/api/v1/enterprises", json={"name": "测试企业", "agent": "张三"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "测试项目"}
    ).json()
    return ent["id"], proj["id"]


def _parse_to_score_parsed(
    db_client: TestClient,
    eid: str,
    pid: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_name: str = "招标文件.pdf",
) -> list[dict[str, Any]]:
    """跑到 SCORE_PARSED 并返回 SSE 事件列表。"""
    src = tmp_path / file_name
    make_text_pdf(src, ["tender " * 20])
    db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/sources",
        json={"files": [{"name": file_name, "path": str(src)}]},
    )
    _patch_engine(monkeypatch, FakeMineruFormat(), {})
    events: list[dict[str, Any]] = []
    with db_client.stream(
        "POST",
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/start",
        json={"reparse": False},
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_get_checklist_returns_full_data(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    events = _parse_to_score_parsed(db_client, eid, pid, tmp_path, monkeypatch)
    assert events[-1]["stage"] == "completed"

    resp = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/checklist")
    assert resp.status_code == 200
    data = resp.json()
    assert data["parse_status"] == "SCORE_PARSED"
    assert data["extraction"] is not None
    assert data["score"] is not None
    assert data["docx"] is not None
    assert data["confirmed"] is None  # 尚未确认


def test_enter_review_transitions_state(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _parse_to_score_parsed(db_client, eid, pid, tmp_path, monkeypatch)

    resp = db_client.post(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/review")
    assert resp.status_code == 200
    assert resp.json()["parse_status"] == "PARSE_REVIEW"

    # 幂等：重复调用不报错
    resp2 = db_client.post(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/review")
    assert resp2.status_code == 200
    assert resp2.json()["parse_status"] == "PARSE_REVIEW"


def test_confirm_rejects_unconfirmed(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _parse_to_score_parsed(db_client, eid, pid, tmp_path, monkeypatch)
    db_client.post(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/review")

    # 提交空 items → 400
    resp = db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/confirm",
        json={"items": []},
    )
    assert resp.status_code == 422  # min_length=1

    # 提交未全 confirmed → 400
    resp = db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/confirm",
        json={
            "items": [
                {"tab": "extraction", "item_id": "fake:0", "confirmed": False},
            ]
        },
    )
    assert resp.status_code == 400
    assert "未确认" in resp.json()["detail"]


def test_confirm_all_confirmed_unlocks(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _parse_to_score_parsed(db_client, eid, pid, tmp_path, monkeypatch)
    db_client.post(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/review")

    # 获取 checklist 收集条目 ID
    checklist = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/checklist").json()
    items = []
    if checklist.get("extraction"):
        for item in checklist["extraction"]["items"]:
            if item.get("selected"):
                if item.get("matches"):
                    for i in range(len(item["matches"])):
                        items.append(
                            {
                                "tab": "extraction",
                                "item_id": f"{item['key']}:{i}",
                                "confirmed": True,
                            }
                        )
                else:
                    items.append(
                        {"tab": "extraction", "item_id": f"{item['key']}:0", "confirmed": True}
                    )
    if checklist.get("score"):
        for ci, cat in enumerate(checklist["score"]["categories"]):
            for ii in range(len(cat["items"])):
                items.append({"tab": "score", "item_id": f"{ci}:{ii}", "confirmed": True})
    if checklist.get("docx"):
        for src in checklist["docx"]["sources"]:
            for sec in src.get("sections") or []:
                if sec.get("state") == "success" and sec.get("checkpoint_key"):
                    items.append(
                        {"tab": "docx", "item_id": sec["checkpoint_key"], "confirmed": True}
                    )

    resp = db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/confirm",
        json={"items": items},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["parse_status"] == "PARSE_CONFIRMED"
    assert result["confirmed_items"] == result["total_items"]

    # checklist 落盘
    assert paths.checklist_path(eid, pid).is_file()

    # status 包含 confirmed 摘要
    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status["parse_status"] == "PARSE_CONFIRMED"
    assert status["confirmed"]["all_confirmed"] is True


def test_project_isolation(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _parse_to_score_parsed(db_client, eid, pid, tmp_path, monkeypatch)

    other_ent = db_client.post(
        "/api/v1/enterprises", json={"name": "其他企业", "agent": "李四"}
    ).json()
    other_proj = db_client.post(
        f"/api/v1/enterprises/{other_ent['id']}/projects", json={"name": "其他项目"}
    ).json()

    resp = db_client.get(
        f"/api/v1/enterprises/{other_ent['id']}/projects/{other_proj['id']}/parse/checklist"
    )
    assert resp.status_code == 200
    other_data = resp.json()
    assert other_data["extraction"] is None  # 无数据


def _collect_all_items(checklist: dict[str, Any]) -> list[dict[str, Any]]:
    """从 checklist 全量数据中收集所有条目并标记 confirmed=True。"""
    items = []
    if checklist.get("extraction"):
        for item in checklist["extraction"]["items"]:
            if not item.get("selected"):
                continue
            if item.get("matches"):
                for i in range(len(item["matches"])):
                    items.append(
                        {"tab": "extraction", "item_id": f"{item['key']}:{i}", "confirmed": True}
                    )
            else:
                items.append(
                    {"tab": "extraction", "item_id": f"{item['key']}:0", "confirmed": True}
                )
    if checklist.get("score"):
        for ci, cat in enumerate(checklist["score"]["categories"]):
            for ii in range(len(cat["items"])):
                items.append({"tab": "score", "item_id": f"{ci}:{ii}", "confirmed": True})
    if checklist.get("docx"):
        for src in checklist["docx"]["sources"]:
            for sec in src.get("sections") or []:
                if sec.get("state") == "success" and sec.get("checkpoint_key"):
                    items.append(
                        {"tab": "docx", "item_id": sec["checkpoint_key"], "confirmed": True}
                    )
    return items


def test_upstream_reset_invalidates_confirmed(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _parse_to_score_parsed(db_client, eid, pid, tmp_path, monkeypatch)
    db_client.post(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/review")

    checklist = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/checklist").json()
    items = _collect_all_items(checklist)
    db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/confirm",
        json={"items": items},
    )

    # 确认状态
    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status["parse_status"] == "PARSE_CONFIRMED"

    # 单项重试（上游）使确认作废
    db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/retry",
        json={"item": "extract:coarse"},
    )

    status2 = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status2["parse_status"] == "SCORE_PARSED"
    assert not paths.checklist_path(eid, pid).is_file()
