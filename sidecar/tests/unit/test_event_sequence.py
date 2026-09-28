"""单元测试：SSE 测试事件序列的正常完成与取消。"""

import asyncio

from app.api.test_events import event_sequence


async def _collect(cancel: asyncio.Event) -> list[dict]:
    return [event async for event in event_sequence("task-x", cancel)]


def test_completed_sequence() -> None:
    events = asyncio.run(_collect(asyncio.Event()))
    assert [e["stage"] for e in events] == [
        "queued",
        "progress",
        "progress",
        "completed",
    ]
    assert [e["percent"] for e in events] == [0, 40, 80, 100]
    assert all(e["extra"]["task_id"] == "task-x" for e in events)


def test_cancelled_sequence() -> None:
    async def scenario() -> list[dict]:
        cancel = asyncio.Event()
        gen = event_sequence("task-y", cancel).__aiter__()
        first = await gen.__anext__()
        assert first["stage"] == "queued"

        # 模拟收到取消请求
        cancel.set()
        rest = [event async for event in gen]
        return [first, *rest]

    events = asyncio.run(scenario())
    assert events[-1]["stage"] == "cancelled"
    assert events[-1]["percent"] == 40
