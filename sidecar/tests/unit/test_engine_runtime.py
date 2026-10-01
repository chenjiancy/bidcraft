"""MinerU 打包分发运行时测试：python 定位优先级、local 模型配置、子进程 env。

覆盖 v0.2.7 安装包分发（resources/mineru/python + resources/mineru/models）
与开发期 .venv-mineru 两条路径的选择逻辑。
"""

import json
import os

from app.parse import engine


def _touch(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_mineru_python_prefers_explicit_env(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(engine.ENV_RESOURCES_PATH, raising=False)
    explicit = tmp_path / "custom" / "python.exe"
    _touch(explicit)
    monkeypatch.setenv(engine.ENV_MINERU_PYTHON, str(explicit))
    monkeypatch.setattr(engine, "_DEFAULT_VENV", tmp_path / "no-such-venv")

    assert engine.mineru_python() == explicit


def test_mineru_python_falls_back_to_packaged_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(engine.ENV_MINERU_PYTHON, raising=False)
    resources = tmp_path / "resources"
    packaged_py = resources / "mineru" / "python" / engine._python_exe_name()
    _touch(packaged_py)
    monkeypatch.setenv(engine.ENV_RESOURCES_PATH, str(resources))
    monkeypatch.setattr(engine, "_DEFAULT_VENV", tmp_path / "no-such-venv")

    assert engine.mineru_python() == packaged_py


def test_mineru_python_returns_none_when_nothing_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(engine.ENV_MINERU_PYTHON, raising=False)
    monkeypatch.delenv(engine.ENV_RESOURCES_PATH, raising=False)
    monkeypatch.setattr(engine, "_DEFAULT_VENV", tmp_path / "no-such-venv")

    assert engine.mineru_python() is None


def test_mineru_argv_uses_module_invocation(tmp_path) -> None:
    py = tmp_path / "python.exe"
    argv = engine._mineru_argv(py)
    assert argv[:2] == [str(py), "-m"]
    assert argv[2] == "mineru.cli.client"


def test_packaged_models_dir_none_without_resources(monkeypatch) -> None:
    monkeypatch.delenv(engine.ENV_RESOURCES_PATH, raising=False)
    assert engine._packaged_models_dir() is None


def test_ensure_config_none_without_packaged_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(engine.ENV_RESOURCES_PATH, str(tmp_path / "resources"))
    monkeypatch.setenv(engine.ENV_DATA_ROOT, str(tmp_path / "data"))
    assert engine.ensure_packaged_mineru_config() is None


def test_ensure_config_none_without_data_root(tmp_path, monkeypatch) -> None:
    resources = tmp_path / "resources"
    (resources / "mineru" / "models").mkdir(parents=True)
    monkeypatch.setenv(engine.ENV_RESOURCES_PATH, str(resources))
    monkeypatch.delenv(engine.ENV_DATA_ROOT, raising=False)
    assert engine.ensure_packaged_mineru_config() is None


def test_ensure_config_writes_local_mode_json_and_is_idempotent(tmp_path, monkeypatch) -> None:
    resources = tmp_path / "resources"
    models = resources / "mineru" / "models"
    models.mkdir(parents=True)
    data_root = tmp_path / "data"
    monkeypatch.setenv(engine.ENV_RESOURCES_PATH, str(resources))
    monkeypatch.setenv(engine.ENV_DATA_ROOT, str(data_root))

    cfg_path = engine.ensure_packaged_mineru_config()
    assert cfg_path is not None
    assert cfg_path == data_root / "mineru" / "mineru.json"

    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert payload["model-source"] == "local"
    assert payload["models-dir"]["pipeline"] == str(models)
    assert payload["config_version"] == engine._MINERU_CONFIG_VERSION

    mtime_before = cfg_path.stat().st_mtime_ns
    # 再次调用内容一致，不重写（幂等）
    cfg_path_2 = engine.ensure_packaged_mineru_config()
    assert cfg_path_2 == cfg_path
    assert cfg_path.stat().st_mtime_ns == mtime_before


def test_child_env_injects_local_mode_for_packaged(tmp_path, monkeypatch) -> None:
    resources = tmp_path / "resources"
    (resources / "mineru" / "models").mkdir(parents=True)
    data_root = tmp_path / "data"
    monkeypatch.setenv(engine.ENV_RESOURCES_PATH, str(resources))
    monkeypatch.setenv(engine.ENV_DATA_ROOT, str(data_root))

    env = engine.mineru_child_env()
    assert env[engine.ENV_MODEL_SOURCE] == "local"
    assert env[engine.ENV_TOOLS_CONFIG_JSON] == str(data_root / "mineru" / "mineru.json")
    assert env["PYTHONUNBUFFERED"] == "1"


def test_child_env_dev_mode_without_injection(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(engine.ENV_RESOURCES_PATH, raising=False)
    monkeypatch.delenv(engine.ENV_MODEL_SOURCE, raising=False)
    monkeypatch.delenv(engine.ENV_TOOLS_CONFIG_JSON, raising=False)

    env = engine.mineru_child_env()
    assert env["PYTHONUNBUFFERED"] == "1"
    assert engine.ENV_MODEL_SOURCE not in env
    assert engine.ENV_TOOLS_CONFIG_JSON not in env


def test_existing_os_environ_not_mutated_by_child_env(tmp_path, monkeypatch) -> None:
    """mineru_child_env 返回新字典，不得就地污染 os.environ（影响 sidecar 其他子进程）。"""
    monkeypatch.delenv(engine.ENV_RESOURCES_PATH, raising=False)
    before = dict(os.environ)
    engine.mineru_child_env()
    assert dict(os.environ) == before
