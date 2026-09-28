"""pytest 公共夹具：每个测试用例使用隔离的临时数据根。

对应 devops-environment.md 第三节"每测试用临时数据库 + 临时数据目录"。
"""

from pathlib import Path

import pytest


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "bidcraft-test"
    monkeypatch.setenv("BIDCRAFT_DATA_ROOT", str(root))
    return root
