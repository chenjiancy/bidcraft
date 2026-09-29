"""Task 16 素材提取清单集成测试（TR-16.1～16.12）。"""

import json

import pytest
from fastapi.testclient import TestClient

from app.db.deps import get_engine
from app.db.session import session_factory
from app.materials import fts5
from app.parse import paths
from app.repositories.base import Scope
from app.repositories.material import MaterialRepository


@pytest.fixture
def project(db_client: TestClient) -> tuple[str, str]:
    ent = db_client.post("/api/v1/enterprises", json={"name": "测试企业", "agent": "张三"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "测试项目"}
    ).json()
    return ent["id"], proj["id"]


def _base(eid: str, pid: str) -> str:
    return f"/api/v1/enterprises/{eid}/projects/{pid}/material-extract"


def _write_score_table(eid: str, pid: str, items: list[dict]) -> None:
    path = paths.score_table_path(eid, pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "scoring_version": "v1",
        "generated_at": "2026-09-29T00:00:00Z",
        "categories": [
            {
                "name": "商务评分",
                "source_chapter": "第三章",
                "subtotal": 10,
                "items": items,
            }
        ],
        "total_score_check": {"expected": 10, "actual": 10, "ok": True},
        "red_flags": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_format_list(eid: str, pid: str, items: list[dict]) -> None:
    path = paths.format_list_path(eid, pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sections": [{"name": "资格文件", "items": items}]}, ensure_ascii=False),
        encoding="utf-8",
    )


def _seed_material(
    eid: str,
    pid: str | None,
    *,
    name: str,
    filename: str,
    ocr_text: str = "",
    category: str = "qualification",
) -> str:
    """直接经 Repository 建素材并写 FTS5 索引（绕过转图/OCR）。"""
    session = session_factory(get_engine())()
    try:
        repo = MaterialRepository(session, Scope(enterprise_id=eid))
        m = repo.create(
            enterprise_id=eid,
            project_id=pid,
            category=category,
            name=name,
            filename=filename,
            file_path=f"/tmp/{filename}.png",
            ocr_text=ocr_text,
        )
        session.commit()
        fts5.fts5_add(paths.fts5_db_path(eid), m.id, m.name, m.ocr_text or "")
        return m.id
    finally:
        session.close()


def _set_status(eid: str, pid: str, status: str) -> None:
    from app.models.project import Project

    session = session_factory(get_engine())()
    try:
        proj = session.get(Project, pid)
        assert proj is not None
        proj.parse_status = status
        session.commit()
    finally:
        session.close()


# ---------- TR-16.1 两源聚合 ----------


def test_generate_aggregates_two_sources_and_dedupes(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    _write_score_table(
        eid,
        pid,
        [
            {
                "name": "监理业绩",
                "score": 5,
                "materials": ["监理合同", "竣工报告"],
                "thresholds": [],
            }
        ],
    )
    # 格式清单中一条 EXTERNAL 项，其材料名与 score_table 重复（应去重）
    _write_format_list(
        eid,
        pid,
        [
            {"name": "监理合同", "status": "EXTERNAL"},
            {"name": "资质证书副本", "status": "EXTERNAL"},
        ],
    )

    resp = db_client.post(f"{_base(eid, pid)}/generate")
    assert resp.status_code == 200
    data = resp.json()
    names = [it["requirement_name"] for it in data["items"]]

    # 监理合同 两源同名只保留一条（去重）；竣工报告、资质证书副本 各一条
    assert data["requirement_count"] == 3
    assert sum(1 for n in names if "监理合同" in n) == 1
    assert any("竣工报告" in n for n in names)
    assert "资质证书副本" in names

    sources = {it["requirement_name"]: it["source"] for it in data["items"]}
    assert sources["资质证书副本"] == "format_clause"
    # score_table 来源条目带来源锚点
    anchors = [it["source_anchor"] for it in data["items"] if it["source"] == "score_table"]
    assert anchors and all(anchors)


def test_generate_is_idempotent_per_round(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    _write_score_table(
        eid,
        pid,
        [{"name": "X", "score": 1, "materials": ["材料A"], "thresholds": []}],
    )
    first = db_client.post(f"{_base(eid, pid)}/generate").json()
    second = db_client.post(f"{_base(eid, pid)}/generate").json()
    assert first["requirement_count"] == second["requirement_count"] == 1
    assert len(db_client.get(f"{_base(eid, pid)}").json()["items"]) == 1


# ---------- TR-16.2 增删改 ----------


def test_add_update_delete_requirement(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    created = db_client.post(f"{_base(eid, pid)}/items", json={"requirement_name": "手工新增材料"})
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    updated = db_client.put(
        f"{_base(eid, pid)}/items/{item_id}", json={"requirement_name": "改名后材料"}
    )
    assert updated.status_code == 200
    assert updated.json()["requirement_name"] == "改名后材料"

    deleted = db_client.delete(f"{_base(eid, pid)}/items/{item_id}")
    assert deleted.status_code == 200
    assert db_client.get(f"{_base(eid, pid)}").json()["total"] == 0


# ---------- TR-16.3/16.4 查询匹配 + 证件组聚合 ----------


def test_query_returns_grouped_candidates(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    _seed_material(eid, None, name="监理资质证书", filename="zcs_监理_20260101", ocr_text="")
    _seed_material(eid, None, name="监理资质证书", filename="zcs_监理_20260101_P1", ocr_text="")

    resp = db_client.post(f"{_base(eid, pid)}/query", json={"keyword": "监理资质证书"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    # 两页聚合成一个证件组
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["group_key"] == "zcs_监理_20260101"


def test_query_matches_ocr_text(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    _seed_material(
        eid, None, name="扫描件", filename="sfz_扫描_20260101", ocr_text="中华人民共和国居民身份证"
    )
    data = db_client.post(f"{_base(eid, pid)}/query", json={"keyword": "居民身份证"}).json()
    assert data["total"] == 1
    assert data["candidates"][0]["items"][0]["name"] == "扫描件"


# ---------- TR-16.12 隔离 ----------


def test_query_isolation_across_enterprises(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid_a, pid_a = project
    ent_b = db_client.post("/api/v1/enterprises", json={"name": "他企业", "agent": "李四"}).json()
    proj_b = db_client.post(
        f"/api/v1/enterprises/{ent_b['id']}/projects", json={"name": "他项目"}
    ).json()

    # A 企业素材
    _seed_material(eid_a, None, name="监理资质证书", filename="zcs_A_20260101")
    # 他企业素材（同关键词）
    _seed_material(ent_b["id"], None, name="监理资质证书", filename="zcs_B_20260101")

    data = db_client.post(f"{_base(eid_a, pid_a)}/query", json={"keyword": "监理资质证书"}).json()
    assert data["total"] == 1
    assert data["candidates"][0]["group_key"] == "zcs_A_20260101"

    # 确保他项目可见自己的
    data_b = db_client.post(
        f"{_base(ent_b['id'], proj_b['id'])}/query", json={"keyword": "监理资质证书"}
    ).json()
    assert data_b["total"] == 1
    assert data_b["candidates"][0]["group_key"] == "zcs_B_20260101"


def test_query_isolation_across_projects_same_enterprise(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    """企业共享可见 + 本项目独享可见；他项目独享不可见。"""
    eid, pid = project
    proj2 = db_client.post(f"/api/v1/enterprises/{eid}/projects", json={"name": "项目二"}).json()

    _seed_material(eid, None, name="共享资质证书", filename="zcs_共享_20260101")
    _seed_material(eid, pid, name="本项目资质证书", filename="zcs_本项目_20260101")
    _seed_material(eid, proj2["id"], name="他项目资质证书", filename="zcs_他项目_20260101")

    data = db_client.post(f"{_base(eid, pid)}/query", json={"keyword": "资质证书"}).json()
    keys = {c["group_key"] for c in data["candidates"]}
    assert "zcs_共享_20260101" in keys
    assert "zcs_本项目_20260101" in keys
    assert "zcs_他项目_20260101" not in keys


# ---------- TR-16.8 多轮留痕 ----------


def test_rounds_are_tracked(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    _write_score_table(
        eid, pid, [{"name": "X", "score": 1, "materials": ["材料A"], "thresholds": []}]
    )
    db_client.post(f"{_base(eid, pid)}/generate")

    resp = db_client.post(f"{_base(eid, pid)}/new-round")
    assert resp.status_code == 200
    assert resp.json()["round"] == 2

    items_r2 = db_client.get(f"{_base(eid, pid)}").json()["items"]
    assert all(it["round"] == 2 for it in items_r2)
    items_r1 = db_client.get(f"{_base(eid, pid)}?round=1").json()["items"]
    assert all(it["round"] == 1 for it in items_r1)


# ---------- TR-16.9 保存门禁 + 清单文件 ----------


def test_confirm_blocked_when_pending(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    _write_score_table(
        eid, pid, [{"name": "X", "score": 1, "materials": ["材料A"], "thresholds": []}]
    )
    db_client.post(f"{_base(eid, pid)}/generate")
    _set_status(eid, pid, "MATERIAL_LOOP")

    resp = db_client.post(f"{_base(eid, pid)}/confirm")
    assert resp.status_code == 400
    assert "未选定" in resp.json()["detail"]


def test_confirm_writes_list_and_transitions(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    _write_score_table(
        eid, pid, [{"name": "X", "score": 1, "materials": ["材料A"], "thresholds": []}]
    )
    db_client.post(f"{_base(eid, pid)}/generate")
    _set_status(eid, pid, "MATERIAL_LOOP")

    item = db_client.get(f"{_base(eid, pid)}").json()["items"][0]
    mat_id = _seed_material(eid, None, name="材料A", filename="zcs_A_20260101")
    change = {
        "item_id": item["id"],
        "status": "selected",
        "selected_material_id": mat_id,
    }
    db_client.post(
        f"{_base(eid, pid)}/save-round",
        json={"round": 1, "changes": [change]},
    )

    resp = db_client.post(f"{_base(eid, pid)}/confirm")
    assert resp.status_code == 200
    assert resp.json()["item_count"] == 1

    # 清单文件落盘（渲染唯一依据）
    list_path = paths.lists_dir(eid, pid) / "material_extract.json"
    assert list_path.exists()
    payload = json.loads(list_path.read_text(encoding="utf-8"))
    assert payload["items"][0]["status"] == "selected"
    assert payload["confirmed_at"]

    # 状态机 → MATERIAL_CONFIRMED
    from app.models.project import Project

    session = session_factory(get_engine())()
    try:
        assert session.get(Project, pid).parse_status == "MATERIAL_CONFIRMED"
    finally:
        session.close()


# ---------- TR-16.10 状态机留痕 ----------


def test_confirm_records_app_event(db_client: TestClient, project: tuple[str, str]) -> None:
    eid, pid = project
    _write_score_table(
        eid, pid, [{"name": "X", "score": 1, "materials": ["材料A"], "thresholds": []}]
    )
    db_client.post(f"{_base(eid, pid)}/generate")
    _set_status(eid, pid, "MATERIAL_LOOP")

    item = db_client.get(f"{_base(eid, pid)}").json()["items"][0]
    db_client.post(
        f"{_base(eid, pid)}/save-round",
        json={"round": 1, "changes": [{"item_id": item["id"], "status": "missing"}]},
    )
    db_client.post(f"{_base(eid, pid)}/confirm")

    from app.models.app_event import AppEvent

    session = session_factory(get_engine())()
    try:
        events = session.query(AppEvent).filter_by(project_id=pid, type="parse_state_change").all()
        assert any(
            e.payload.get("to") == "MATERIAL_CONFIRMED" and e.payload.get("from") == "MATERIAL_LOOP"
            for e in events
        )
    finally:
        session.close()


def test_confirm_rejects_illegal_state(db_client: TestClient, project: tuple[str, str]) -> None:
    """非 MATERIAL_LOOP 状态不得保存（如 SCORE_PARSED）。"""
    eid, pid = project
    _write_score_table(
        eid, pid, [{"name": "X", "score": 1, "materials": ["材料A"], "thresholds": []}]
    )
    db_client.post(f"{_base(eid, pid)}/generate")
    _set_status(eid, pid, "SCORE_PARSED")

    item = db_client.get(f"{_base(eid, pid)}").json()["items"][0]
    db_client.post(
        f"{_base(eid, pid)}/save-round",
        json={"round": 1, "changes": [{"item_id": item["id"], "status": "missing"}]},
    )
    resp = db_client.post(f"{_base(eid, pid)}/confirm")
    assert resp.status_code == 400


# ---------- TR-16.6 A 类处理（库外文件） ----------


def test_import_external_missing_file_returns_400(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    resp = db_client.post(
        f"{_base(eid, pid)}/import-external",
        json={"file_path": "Z:/not/exist.pdf", "category": "qualification"},
    )
    assert resp.status_code == 400
