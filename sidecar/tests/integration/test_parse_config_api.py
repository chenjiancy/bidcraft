"""Task 9 解析配置集成测试（TR-9.1 形态由后端目录保证 / TR-9.2 / TR-9.3 / TR-9.4）。"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.deps import get_engine
from app.db.session import session_factory
from app.models.app_event import AppEvent
from app.models.project import Project
from app.parse import config as cfg


@pytest.fixture
def project(db_client: TestClient) -> tuple[str, str]:
    ent = db_client.post("/api/v1/enterprises", json={"name": "测试企业", "agent": "张三"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "测试项目"}
    ).json()
    return ent["id"], proj["id"]


def _route(eid: str, pid: str) -> str:
    return f"/api/v1/enterprises/{eid}/projects/{pid}/parse/config"


def _required() -> list[str]:
    return sorted(cfg.REQUIRED_KEYS)


def _set_parse_status(pid: str, status: str) -> None:
    with session_factory(get_engine())() as session:
        project = session.scalars(select(Project).where(Project.id == pid)).one()
        project.parse_status = status
        session.commit()


# ---------- TR-9.3：默认配置 + 项目级落库 ----------


def test_get_config_returns_defaults_when_never_saved(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    resp = db_client.get(_route(eid, pid))
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_default"] is True
    assert len(data["items"]) == 18
    required = [i for i in data["items"] if i["required"]]
    optional = [i for i in data["items"] if not i["required"]]
    assert len(required) == 8 and all(i["selected"] for i in required)
    assert len(optional) == 10 and all(not i["selected"] for i in optional)
    assert data["llm_enabled"] is False
    assert data["llm_mode"] == "validate"


def test_put_then_get_persists_project_scoped(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    body = {
        "selected": [*_required(), "bid_bond", "bid_opening"],
        "llm_enabled": True,
        "llm_mode": "dual_channel",
    }
    saved = db_client.put(_route(eid, pid), json=body)
    assert saved.status_code == 200
    out = saved.json()
    assert out["config"]["is_default"] is False
    assert out["reparse_required"] is False  # INIT 态保存无需重解析

    again = db_client.get(_route(eid, pid)).json()
    assert again["is_default"] is False
    picked = {i["key"]: i["selected"] for i in again["items"]}
    assert picked["bid_bond"] is True and picked["bid_opening"] is True
    assert picked["procurement_list"] is False
    assert again["llm_enabled"] is True and again["llm_mode"] == "dual_channel"


def test_other_project_still_sees_default(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, _ = project
    pid_a = db_client.post(f"/api/v1/enterprises/{eid}/projects", json={"name": "项目A"}).json()[
        "id"
    ]
    pid_b = db_client.post(f"/api/v1/enterprises/{eid}/projects", json={"name": "项目B"}).json()[
        "id"
    ]
    db_client.put(_route(eid, pid_a), json={"selected": [*_required(), "bid_bond"]})

    data_b = db_client.get(_route(eid, pid_b)).json()
    assert data_b["is_default"] is True
    assert all(i["selected"] is False for i in data_b["items"] if i["key"] == "bid_bond")


def test_cross_enterprise_access_is_404(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    other = db_client.post("/api/v1/enterprises", json={"name": "别家企业", "agent": "李四"}).json()
    resp = db_client.get(_route(other["id"], pid))
    assert resp.status_code == 404
    resp_put = db_client.put(_route(other["id"], pid), json={"selected": _required()})
    assert resp_put.status_code == 404


# ---------- TR-9.2 / 校验规则 ----------


def test_required_item_cannot_be_deselected(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    resp = db_client.put(
        _route(eid, pid), json={"selected": sorted(cfg.REQUIRED_KEYS - {"invalid_bid"})}
    )
    assert resp.status_code == 400
    assert "必选" in resp.json()["detail"]


def test_unknown_item_rejected(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    resp = db_client.put(_route(eid, pid), json={"selected": [*_required(), "bogus"]})
    assert resp.status_code == 400


def test_llm_enabled_requires_valid_mode(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    resp = db_client.put(_route(eid, pid), json={"selected": _required(), "llm_enabled": True})
    assert resp.status_code == 400
    resp2 = db_client.put(
        _route(eid, pid),
        json={"selected": _required(), "llm_enabled": True, "llm_mode": "bogus"},
    )
    assert resp2.status_code == 400


def test_llm_disabled_normalizes_mode_to_validate(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    resp = db_client.put(
        _route(eid, pid),
        json={"selected": _required(), "llm_enabled": False, "llm_mode": "dual_channel"},
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["llm_mode"] == "validate"


# ---------- TR-9.4：PARSED 后变更提示 + 操作日志 ----------


def _config_change_events(pid: str) -> list[dict[str, Any]]:
    with session_factory(get_engine())() as session:
        rows = session.scalars(
            select(AppEvent)
            .where(AppEvent.project_id == pid)
            .where(AppEvent.type == "parse_config_change")
        ).all()
        return [r.payload or {} for r in rows]


def test_change_after_parsed_flags_reparse_and_logs(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    _set_parse_status(pid, "PARSED")

    resp = db_client.put(
        _route(eid, pid),
        json={"selected": [*_required(), "bid_bond"], "llm_enabled": True, "llm_mode": "validate"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reparse_required"] is True
    # Task 9：物理层 checkpoint 不消费配置，受影响单项为空（Task 10 扩展）
    assert data["affected_items"] == []
    assert data["changes"]["selected_added"] == ["bid_bond"]
    assert data["changes"]["llm_enabled"] == {"from": False, "to": True}

    events = _config_change_events(pid)
    assert len(events) == 1
    assert events[0]["changes"]["selected_added"] == ["bid_bond"]


def test_no_change_does_not_log_or_flag(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    _set_parse_status(pid, "PARSED")
    resp = db_client.put(_route(eid, pid), json={"selected": _required()})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reparse_required"] is False
    assert data["changes"] == {}
    assert _config_change_events(pid) == []


def test_change_before_parsing_does_not_require_reparse(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    _set_parse_status(pid, "UPLOADED")
    resp = db_client.put(_route(eid, pid), json={"selected": [*_required(), "bid_bond"]})
    assert resp.status_code == 200
    assert resp.json()["reparse_required"] is False


def test_config_change_rejected_while_job_running(
    db_client: TestClient, project: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    eid, pid = project
    from app.api import parse as parse_api

    monkeypatch.setattr(parse_api.job_manager, "is_running", lambda *a: True)
    resp = db_client.put(_route(eid, pid), json={"selected": [*_required(), "bid_bond"]})
    assert resp.status_code == 409
