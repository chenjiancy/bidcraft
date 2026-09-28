"""config 数据根解析单元测试。"""

from pathlib import Path

import pytest

from app.core import config


def test_resolve_data_root_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(tmp_path / "x"))
    assert config.resolve_data_root() == tmp_path / "x"


def test_resolve_data_root_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BIDCRAFT_DATA_ROOT", raising=False)
    assert config.resolve_data_root() == config.FALLBACK_DATA_ROOT
