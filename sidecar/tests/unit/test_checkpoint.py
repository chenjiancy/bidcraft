"""BP-1 Checkpoint 框架单元测试（TR-8.7 断点续跑/单项重试的基础）。"""

import json
from pathlib import Path

from app.parse.checkpoint import CheckpointItem, CheckpointStore

_LABELS = {"a": "阶段A", "b": "阶段B"}


def _store(path: Path) -> CheckpointStore:
    return CheckpointStore.load_or_create(path / "job.json", "job", _LABELS)


def test_new_store_has_idle_items(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert set(store.items) == {"a", "b"}
    assert all(item.state == "idle" for item in store.items.values())
    assert (tmp_path / "job.json").is_file()


def test_state_transitions_and_attempts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.mark_running("a")
    assert store.get("a").state == "running"
    assert store.get("a").attempts == 1
    store.mark_success("a", {"x": 1})
    assert store.state == "idle"  # b 仍 idle

    store.mark_running("b")
    store.mark_error("b", "boom")
    assert store.state == "error"
    assert store.get("b").error == "boom"
    summary = store.summary()
    assert summary["counts"] == {"success": 1, "error": 1}


def test_persistence_roundtrip_keeps_success(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.mark_running("a")
    store.mark_success("a", {"k": "v"})
    store.mark_running("b")
    store.mark_error("b", "bad")

    reopened = _store(tmp_path)
    assert reopened.get("a").state == "success"
    assert reopened.get("a").output == {"k": "v"}
    # error 不会自动清（reset_pending 才清）
    assert reopened.get("b").state == "error"


def test_crashed_running_recovers_to_idle(tmp_path: Path) -> None:
    """进程崩溃留下 running：重新加载回置 idle，续跑可重新执行。"""
    path = tmp_path / "job.json"
    store = _store(tmp_path)
    store.mark_running("a")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["items"]["a"]["state"] == "running"

    reopened = _store(tmp_path)
    assert reopened.get("a").state == "idle"
    assert reopened.get("a").error  # 留有中断说明


def test_reset_pending_clears_only_error(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.mark_success("a")
    store.mark_running("b")
    store.mark_error("b", "x")
    store.reset_pending()
    assert store.get("a").state == "success"
    assert store.get("b").state == "idle"
    assert store.get("b").error is None
    assert store.get("b").attempts == 1  # 尝试次数保留


def test_dynamic_new_items_preserve_existing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.mark_success("a", {"old": True})
    store._add_new_items({"c": "动态阶段C"})
    assert store.get("a").output == {"old": True}
    assert store.get("c").state == "idle"

    # 再次加载：初始 labels + 动态项都在
    reopened = _store(tmp_path)
    assert set(reopened.items) == {"a", "b", "c"}


def test_reset_and_delete(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.mark_success("a", {"x": 1})
    store.reset("a")
    assert store.get("a").state == "idle"
    assert store.get("a").output is None

    store._add_new_items({"dyn": "动态"})
    store.delete("dyn")
    assert "dyn" not in store.items
    store.delete("dyn")  # 删除不存在项不报错


def test_atomic_write_no_tmp_left(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.mark_running("a")
    store.mark_success("a")
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_item_from_dict_tolerates_missing_fields(tmp_path: Path) -> None:
    item = CheckpointItem.from_dict({"key": "x"})
    assert item.key == "x"
    assert item.state == "idle"
    assert item.attempts == 0
