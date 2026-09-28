"""TR-5.1/5.2/5.3：企业/项目 CRUD + 代理人优先级 + 回收站。"""

from fastapi.testclient import TestClient

# ========== TR-5.1: 创建 + 切换企业后互不可见 ==========


def test_create_enterprise(db_client: TestClient) -> None:
    """TR-5.1: 可创建企业。"""
    resp = db_client.post(
        "/api/v1/enterprises",
        json={"name": "测试企业", "agent": "张三"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试企业"
    assert data["agent"] == "张三"
    assert data["status"] == "active"
    assert "id" in data


def test_create_project_under_enterprise(db_client: TestClient) -> None:
    """TR-5.1: 可在企业下创建项目。"""
    ent = db_client.post(
        "/api/v1/enterprises",
        json={"name": "甲企业", "agent": "李四"},
    ).json()
    resp = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects",
        json={"name": "监理项目A"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "监理项目A"
    assert data["enterprise_id"] == ent["id"]
    assert data["agent"] == "李四"  # 未指定 agent → 回退企业


def test_list_projects_cross_enterprise_invisible(db_client: TestClient) -> None:
    """TR-5.1: 切换企业后项目互不可见。"""
    ent_a = db_client.post(
        "/api/v1/enterprises", json={"name": "甲企业", "agent": "A代理人"}
    ).json()
    ent_b = db_client.post(
        "/api/v1/enterprises", json={"name": "乙企业", "agent": "B代理人"}
    ).json()
    db_client.post(f"/api/v1/enterprises/{ent_a['id']}/projects", json={"name": "A项目"})
    db_client.post(f"/api/v1/enterprises/{ent_b['id']}/projects", json={"name": "B项目"})

    resp_a = db_client.get(f"/api/v1/enterprises/{ent_a['id']}/projects")
    assert resp_a.status_code == 200
    assert {p["name"] for p in resp_a.json()} == {"A项目"}

    resp_b = db_client.get(f"/api/v1/enterprises/{ent_b['id']}/projects")
    assert {p["name"] for p in resp_b.json()} == {"B项目"}


def test_get_project_cross_enterprise_blocked(db_client: TestClient) -> None:
    """TR-5.1: 跨企业访问项目详情被拦截（404）。"""
    ent_a = db_client.post("/api/v1/enterprises", json={"name": "甲企业", "agent": "A"}).json()
    ent_b = db_client.post("/api/v1/enterprises", json={"name": "乙企业", "agent": "B"}).json()
    proj_a = db_client.post(
        f"/api/v1/enterprises/{ent_a['id']}/projects", json={"name": "A项目"}
    ).json()

    # 用 B 企业路径访问 A 的项目 → 404
    resp = db_client.get(f"/api/v1/enterprises/{ent_b['id']}/projects/{proj_a['id']}")
    assert resp.status_code == 404


# ========== TR-5.2: 代理人必填 + 回退 ==========


def test_enterprise_agent_required(db_client: TestClient) -> None:
    """TR-5.2: 企业委托代理人必填拦截（空串 → 422）。"""
    resp = db_client.post(
        "/api/v1/enterprises",
        json={"name": "无代理人企业", "agent": ""},
    )
    assert resp.status_code == 422


def test_project_agent_fallback_to_enterprise(db_client: TestClient) -> None:
    """TR-5.2: 项目缺省时回退企业代理人。"""
    ent = db_client.post(
        "/api/v1/enterprises",
        json={"name": "企业X", "agent": "王五"},
    ).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects",
        json={"name": "项目1"},
    ).json()
    assert proj["agent"] == "王五"

    proj2 = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects",
        json={"name": "项目2", "agent": "赵六"},
    ).json()
    assert proj2["agent"] == "赵六"


def test_update_project_agent_clear_fallback(db_client: TestClient) -> None:
    """TR-5.2: 项目 agent 清空后回退企业 agent。"""
    ent = db_client.post("/api/v1/enterprises", json={"name": "企业W", "agent": "王五"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects",
        json={"name": "项目", "agent": "项目代理人"},
    ).json()
    resp = db_client.put(
        f"/api/v1/enterprises/{ent['id']}/projects/{proj['id']}",
        json={"agent": None},
    )
    assert resp.status_code == 200
    assert resp.json()["agent"] == "王五"


# ========== TR-5.3: 删除进回收站 + 恢复 ==========


def test_delete_enterprise_goes_to_recycle_bin(db_client: TestClient) -> None:
    """TR-5.3: 删除企业进入回收站而非物理删除。"""
    ent = db_client.post("/api/v1/enterprises", json={"name": "待删企业", "agent": "钱七"}).json()
    ent_id = ent["id"]

    resp = db_client.delete(f"/api/v1/enterprises/{ent_id}")
    assert resp.status_code == 204

    # 企业列表中不再可见
    ents = db_client.get("/api/v1/enterprises").json()
    assert all(e["id"] != ent_id for e in ents)

    # 回收站中有记录
    bin_items = db_client.get("/api/v1/recycle-bin").json()
    assert any(i["item_type"] == "enterprise" and i["ref_id"] == ent_id for i in bin_items)


def test_delete_project_goes_to_recycle_bin(db_client: TestClient) -> None:
    """TR-5.3: 删除项目进入回收站。"""
    ent = db_client.post("/api/v1/enterprises", json={"name": "企业Y", "agent": "孙八"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "待删项目"}
    ).json()
    proj_id = proj["id"]

    resp = db_client.delete(f"/api/v1/enterprises/{ent['id']}/projects/{proj_id}")
    assert resp.status_code == 204

    projs = db_client.get(f"/api/v1/enterprises/{ent['id']}/projects").json()
    assert all(p["id"] != proj_id for p in projs)

    bin_items = db_client.get("/api/v1/recycle-bin").json()
    assert any(i["item_type"] == "project" and i["ref_id"] == proj_id for i in bin_items)


def test_restore_enterprise_from_recycle_bin(db_client: TestClient) -> None:
    """回收站恢复：企业恢复后重新出现在列表。"""
    ent = db_client.post("/api/v1/enterprises", json={"name": "恢复企业", "agent": "周九"}).json()
    ent_id = ent["id"]

    db_client.delete(f"/api/v1/enterprises/{ent_id}")
    bin_items = db_client.get("/api/v1/recycle-bin").json()
    item_id = next(
        i["id"] for i in bin_items if i["item_type"] == "enterprise" and i["ref_id"] == ent_id
    )

    resp = db_client.post(f"/api/v1/recycle-bin/{item_id}/restore")
    assert resp.status_code == 200

    ents = db_client.get("/api/v1/enterprises").json()
    assert any(e["id"] == ent_id for e in ents)

    bin_items2 = db_client.get("/api/v1/recycle-bin").json()
    assert all(i["id"] != item_id for i in bin_items2)


def test_purge_recycle_bin_item(db_client: TestClient) -> None:
    """回收站物理清除。"""
    ent = db_client.post("/api/v1/enterprises", json={"name": "清除企业", "agent": "吴十"}).json()
    db_client.delete(f"/api/v1/enterprises/{ent['id']}")
    bin_items = db_client.get("/api/v1/recycle-bin").json()
    item_id = bin_items[0]["id"]

    resp = db_client.delete(f"/api/v1/recycle-bin/{item_id}")
    assert resp.status_code == 204

    bin_items2 = db_client.get("/api/v1/recycle-bin").json()
    assert all(i["id"] != item_id for i in bin_items2)


# ========== 编辑 ==========


def test_update_enterprise(db_client: TestClient) -> None:
    """企业编辑。"""
    ent = db_client.post("/api/v1/enterprises", json={"name": "原名", "agent": "吴十"}).json()
    resp = db_client.put(
        f"/api/v1/enterprises/{ent['id']}",
        json={"name": "新名", "phone": "13800138000"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新名"
    assert data["phone"] == "13800138000"
    assert data["agent"] == "吴十"


def test_update_project(db_client: TestClient) -> None:
    """项目编辑。"""
    ent = db_client.post("/api/v1/enterprises", json={"name": "企业Z", "agent": "郑十一"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects",
        json={"name": "原名", "agent": "项目代理人"},
    ).json()
    resp = db_client.put(
        f"/api/v1/enterprises/{ent['id']}/projects/{proj['id']}",
        json={"name": "新名", "code": "PRJ-001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新名"
    assert data["code"] == "PRJ-001"
    assert data["agent"] == "项目代理人"
