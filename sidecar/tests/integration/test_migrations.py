"""TR-4.1：迁移从零建库（DB 文件 + 表清单为证）。"""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
EXPECTED_TABLES = {
    "enterprise",
    "project",
    "config_kv",
    "app_event",
}


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_migration_builds_database_from_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_root = tmp_path / "freshdata"
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(data_root))
    db_path = data_root / "bidcraft.db"

    # 迁移前：文件不存在
    assert not db_path.exists()

    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")

    # 迁移后：DB 文件存在，含全部核心表与版本表
    assert db_path.exists()
    tables = _table_names(db_path)
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables

    # 关键列存在性抽查（隔离边界列）
    with sqlite3.connect(db_path) as conn:
        project_cols = {row[1] for row in conn.execute("PRAGMA table_info(project)").fetchall()}
    assert {"id", "enterprise_id", "name", "deleted_at"} <= project_cols


def test_migration_downgrade_removes_tables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_root = tmp_path / "downgradedata"
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(data_root))
    db_path = data_root / "bidcraft.db"

    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _table_names(db_path)

    command.downgrade(cfg, "base")
    remaining = _table_names(db_path)
    assert EXPECTED_TABLES.isdisjoint(remaining)
