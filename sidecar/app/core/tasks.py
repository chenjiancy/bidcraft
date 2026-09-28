"""内存异步任务注册表（Task 3 最小版）。

当前仅承载取消信号（NFR-2）；任务持久化/重启恢复不在本任务范围。
"""

import asyncio


class TaskRegistry:
    def __init__(self) -> None:
        self._cancel_events: dict[str, asyncio.Event] = {}

    def register(self, task_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._cancel_events[task_id] = event
        return event

    def request_cancel(self, task_id: str) -> bool:
        """对在册任务设置取消信号；任务不存在或已结束返回 False。"""
        event = self._cancel_events.get(task_id)
        if event is None:
            return False
        event.set()
        return True

    def discard(self, task_id: str) -> None:
        self._cancel_events.pop(task_id, None)


registry = TaskRegistry()
