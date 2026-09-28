"""pytest 公共夹具：每个测试用例使用隔离的临时数据根。

对应 devops-environment.md 第三节"每测试用临时数据库 + 临时数据目录"。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.deps import get_engine, reset_engine
from app.main import app


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "bidcraft-test"
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(root))
    reset_engine()
    return root


@pytest.fixture
def db_client(data_root: Path) -> TestClient:
    """带建表的 TestClient：每用例隔离数据库（企业/项目 API 测试用）。"""
    Base.metadata.create_all(get_engine())
    yield TestClient(app)
    reset_engine()
