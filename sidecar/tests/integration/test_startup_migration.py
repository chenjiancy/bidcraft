"""启动时自动迁移：全新数据根不再空库，且重复执行安全。

对应缺陷：sidecar 启动不跑 Alembic 迁移，全新 userData 首次启动即为空库，
业务接口全部 500（`no such table: enterprise`）。
"""

import sqlite3
from pathlib import Path

import pytest

from app.db.migrate import run_migrations

EXPECTED_TABLES = {"enterprise", "project", "config_kv", "app_event"}


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_run_migrations_builds_database_from_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """全新数据根：调用后库文件与全部核心表就位。"""
    data_root = tmp_path / "freshdata"
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(data_root))
    db_path = data_root / "bidcraft.db"
    assert not db_path.exists()

    run_migrations()

    assert db_path.exists()
    tables = _table_names(db_path)
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables


def test_run_migrations_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """已是 head 时重复执行不报错、不改变表集合（每次启动都会调用）。"""
    data_root = tmp_path / "repeated"
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(data_root))
    db_path = data_root / "bidcraft.db"

    run_migrations()
    before = _table_names(db_path)

    run_migrations()

    assert _table_names(db_path) == before


def test_startup_hook_runs_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动钩子必须调用迁移（防止后续被误删而回归）。"""
    called: list[str] = []
    monkeypatch.setattr("app.main.run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr("app.main.start_cleanup_scheduler", lambda: called.append("cleanup"))

    from app.main import _startup

    _startup()

    assert called == ["migrations", "cleanup"]


def test_startup_hook_propagates_migration_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """迁移失败必须向上抛出，不能降级为继续服务。"""

    def _boom() -> None:
        raise RuntimeError("迁移失败")

    monkeypatch.setattr("app.main.run_migrations", _boom)

    from app.main import _startup

    with pytest.raises(RuntimeError, match="迁移失败"):
        _startup()
