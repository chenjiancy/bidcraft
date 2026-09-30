"""pytest 公共夹具：每个测试用例使用隔离的临时数据根。

对应 devops-environment.md 第三节"每测试用临时数据库 + 临时数据目录"。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.deps import reset_engine
from app.db.migrate import run_migrations
from app.main import app


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "bidcraft-test"
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(root))
    reset_engine()
    return root


@pytest.fixture
def db_client(data_root: Path) -> TestClient:
    """带建库的 TestClient：每用例隔离数据库（企业/项目 API 测试用）。

    建库走 Alembic 迁移而非 ``Base.metadata.create_all``：迁移是 sidecar
    启动时的唯一建库入口（``app.main._startup`` 会调 ``run_migrations``），
    若测试另行 create_all，startup 再迁移就会撞上
    ``table enterprise already exists``。迁移本身幂等，重复调用安全。
    """
    run_migrations()
    yield TestClient(app)
    reset_engine()
