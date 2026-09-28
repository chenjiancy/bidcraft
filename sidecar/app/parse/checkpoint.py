"""BP-1 长任务 Checkpoint 框架（Task 8 建立，Task 9-13 复用）。

设计：
- 每个长任务一份 JSON 落盘（``<project>/parse/checkpoints/<job>.json``）；
- 任务拆为独立 item，每项状态 ``idle/running/success/error`` + 产出 + 错误信息；
- 中断/崩溃后重启只跑未 success 的 item（断点续跑）；
- 单项可 reset 后重跑（单项重试）；
- 写入走临时文件 + ``os.replace`` 原子替换；同文件进程内加锁串行化。

JSON 结构::

    {
      "job_type": "document_parse",
      "created_at": "...", "updated_at": "...",
      "items": {
        "mineru:xxx.pdf": {"state": "success", "attempts": 1, "output": {...}, ...}
      }
    }
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

ItemState = Literal["idle", "running", "success", "error"]
JobState = Literal["idle", "running", "success", "error"]

_FILE_LOCKS: dict[str, threading.Lock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _FILE_LOCKS_GUARD:
        lock = _FILE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _FILE_LOCKS[key] = lock
        return lock


@dataclass
class CheckpointItem:
    """单个 checkpoint 项（一个文件/一个阶段）。"""

    key: str
    label: str
    state: ItemState = "idle"
    attempts: int = 0
    output: dict[str, Any] | None = None
    error: str | None = None
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointItem:
        return cls(
            key=data["key"],
            label=data.get("label", data["key"]),
            state=data.get("state", "idle"),
            attempts=data.get("attempts", 0),
            output=data.get("output"),
            error=data.get("error"),
            updated_at=data.get("updated_at", _now()),
        )


class CheckpointStore:
    """单个长任务的 checkpoint 读写器。"""

    def __init__(self, path: Path, job_type: str, items: dict[str, CheckpointItem]):
        self.path = path
        self.job_type = job_type
        self.created_at = _now()
        self.updated_at = self.created_at
        self.items = items
        self._lock = _lock_for(path)

    # ---------- 持久化 ----------

    @classmethod
    def load_or_create(
        cls,
        path: Path,
        job_type: str,
        item_labels: dict[str, str],
    ) -> CheckpointStore:
        """载入已有 checkpoint；不存在则按 item_labels 新建。

        已存在时按 item_labels 补充新增项（配置变更后新增解析项的场景），
        既有项状态与产出原样保留（断点续跑的核心保证）。
        """
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            items = {k: CheckpointItem.from_dict(v) for k, v in data.get("items", {}).items()}
            store = cls(
                path=path,
                job_type=data.get("job_type", job_type),
                items=items,
            )
            store.created_at = data.get("created_at", store.created_at)
            store.updated_at = data.get("updated_at", store.updated_at)
            # 进程崩溃可能留下 running 项：恢复时回置 idle 以便重跑
            for item in store.items.values():
                if item.state == "running":
                    item.state = "idle"
                    item.error = "进程中断，状态由 running 回置 idle"
            store._add_new_items(item_labels)
            return store

        items = {key: CheckpointItem(key=key, label=label) for key, label in item_labels.items()}
        store = cls(path=path, job_type=job_type, items=items)
        store.save()
        return store

    def _add_new_items(self, item_labels: dict[str, str]) -> None:
        changed = False
        for key, label in item_labels.items():
            if key not in self.items:
                self.items[key] = CheckpointItem(key=key, label=label)
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.updated_at = _now()
            payload = {
                "job_type": self.job_type,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "state": self.state,
                "items": {k: v.to_dict() for k, v in self.items.items()},
            }
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    # ---------- 状态流转 ----------

    @property
    def state(self) -> JobState:
        states = [item.state for item in self.items.values()]
        if not states:
            return "idle"
        if any(s == "running" for s in states):
            return "running"
        if all(s == "success" for s in states):
            return "success"
        if any(s == "error" for s in states):
            return "error"
        return "idle"

    def get(self, key: str) -> CheckpointItem:
        return self.items[key]

    def pending_keys(self) -> list[str]:
        """所有未成功项（续跑清单：中断/失败/新增项都在此）。"""
        return [k for k, item in self.items.items() if item.state != "success"]

    def mark_running(self, key: str) -> None:
        item = self.items[key]
        item.state = "running"
        item.attempts += 1
        item.error = None
        item.updated_at = _now()
        self.save()

    def mark_success(self, key: str, output: dict[str, Any] | None = None) -> None:
        item = self.items[key]
        item.state = "success"
        item.output = output
        item.error = None
        item.updated_at = _now()
        self.save()

    def mark_error(self, key: str, error: str) -> None:
        item = self.items[key]
        item.state = "error"
        item.error = error[:1000]
        item.updated_at = _now()
        self.save()

    def reset(self, key: str) -> None:
        """单项重试：回置 idle 并清除错误/旧产出。"""
        item = self.items[key]
        item.state = "idle"
        item.error = None
        item.output = None
        item.updated_at = _now()
        self.save()

    def delete(self, key: str) -> None:
        """删除动态注册项（上游重跑后该项可能不再存在）。"""
        if key in self.items:
            del self.items[key]
            self.save()

    def reset_pending(self) -> None:
        """整任务续跑前的归一化（error → idle；success 保留）。"""
        changed = False
        for item in self.items.values():
            if item.state == "error":
                item.state = "idle"
                item.error = None
                changed = True
        if changed:
            self.save()

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.items.values():
            counts[item.state] = counts.get(item.state, 0) + 1
        return {
            "job_type": self.job_type,
            "state": self.state,
            "counts": counts,
            "updated_at": self.updated_at,
            "items": [v.to_dict() for v in self.items.values()],
        }
