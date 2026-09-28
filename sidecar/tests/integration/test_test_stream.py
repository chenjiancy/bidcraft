"""集成测试：本地令牌鉴权、SSE 测试事件流与取消。"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.tasks import registry
from app.main import app

TOKEN = "test-sidecar-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _parse_data_lines(lines: list[str]) -> list[dict]:
    events = []
    for line in lines:
        if line.startswith("data:"):
            events.append(json.loads(line.removeprefix("data:").strip()))
    return events


@pytest.fixture
def client(data_root: None, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("BIDCRAFT_SIDECAR_TOKEN", TOKEN)
    return TestClient(app)


def test_requires_token(client: TestClient) -> None:
    assert client.post("/api/v1/test/stream").status_code == 401
    assert (
        client.post(
            "/api/v1/test/stream",
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code
        == 401
    )


def test_full_event_sequence(client: TestClient) -> None:
    lines: list[str] = []
    with client.stream("POST", "/api/v1/test/stream", headers=AUTH) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            lines.append(line)

    events = _parse_data_lines(lines)
    assert [e["stage"] for e in events] == [
        "queued",
        "progress",
        "progress",
        "completed",
    ]
    assert [e["percent"] for e in events] == [0, 40, 80, 100]
    assert events[-1]["stage"] == "completed"
    task_ids = {e["extra"]["task_id"] for e in events}
    assert len(task_ids) == 1


def test_cancel_registered_task(client: TestClient) -> None:
    # TestClient 不支持并发请求，直接预注册任务验证取消端点
    event = registry.register("registered-task")
    try:
        resp = client.post("/api/v1/tasks/registered-task/cancel", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"cancelled": True, "task_id": "registered-task"}
        assert event.is_set()
    finally:
        registry.discard("registered-task")


def test_cancel_unknown_task_404(client: TestClient) -> None:
    resp = client.post("/api/v1/tasks/nonexistent/cancel", headers=AUTH)
    assert resp.status_code == 404


def test_no_token_configured_allows_local_run(
    data_root: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BIDCRAFT_SIDECAR_TOKEN", raising=False)
    bare = TestClient(app)
    resp = bare.post("/api/v1/test/stream")
    assert resp.status_code == 200
