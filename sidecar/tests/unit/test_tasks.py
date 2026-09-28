"""单元测试：内存任务注册表。"""

import asyncio

from app.core.tasks import TaskRegistry


def test_register_and_cancel() -> None:
    reg = TaskRegistry()
    event = reg.register("t1")
    assert not event.is_set()

    assert reg.request_cancel("t1") is True
    assert event.is_set()


def test_cancel_unknown_returns_false() -> None:
    reg = TaskRegistry()
    assert reg.request_cancel("nope") is False


def test_discard_removes_task() -> None:
    reg = TaskRegistry()
    reg.register("t2")
    reg.discard("t2")
    assert reg.request_cancel("t2") is False


def test_async_event_with_running_loop() -> None:
    # FastAPI 端点在事件循环内使用 Event，验证可正常创建与置位
    async def scenario() -> None:
        reg = TaskRegistry()
        event = reg.register("t3")
        reg.request_cancel("t3")
        assert event.is_set()

    asyncio.run(scenario())
