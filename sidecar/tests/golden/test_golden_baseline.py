"""黄金样本基线（占位）：/health 响应与固化快照比对。

真实招标文件样本与解析基线在 Task 8 接入（spec EM-1 / architecture 9.2）。
本测试先固化 golden 机制（夹具目录、快照对比、CI 触发）。
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "health_expected.json"


def test_health_matches_golden(data_root: None) -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json() == expected
