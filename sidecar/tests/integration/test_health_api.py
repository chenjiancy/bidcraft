"""集成测试：FastAPI /health 链路（TestClient）。"""

from fastapi.testclient import TestClient

from app.main import app


def test_health(data_root: None) -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
