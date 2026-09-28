"""Task 3 通信骨架验证端点。

提供确定性 SSE 事件序列与取消入口，用于验证 Main ↔ Python 的
REST + SSE 协议；真实业务端点（/parse/document 等）在后续 Task 落地。
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.security import require_sidecar_token
from app.core.tasks import registry

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])

# 终态前的确定性事件步骤
_STEPS = [
    ("queued", 0, "任务已创建"),
    ("progress", 40, "处理中 1/2"),
    ("progress", 80, "处理中 2/2"),
]
_CANCEL_WINDOW_SECONDS = 0.1


async def event_sequence(
    task_id: str,
    cancel_event: asyncio.Event,
) -> AsyncIterator[dict]:
    """SSE 测试事件序列（dict 形态）。

    每步先等待取消窗口：收到取消信号则以 ``cancelled`` 终态结束；
    正常走完则以 ``completed`` 终态结束。
    """
    terminal = ("completed", 100, "完成")
    for stage, percent, message in _STEPS:
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=_CANCEL_WINDOW_SECONDS)
        except TimeoutError:
            pass
        else:
            terminal = ("cancelled", percent, "任务已取消")
            break

        yield {
            "stage": stage,
            "percent": percent,
            "message": message,
            "extra": {"task_id": task_id},
        }

    stage, percent, message = terminal
    yield {
        "stage": stage,
        "percent": percent,
        "message": message,
        "extra": {"task_id": task_id},
    }


@router.post("/test/stream")
async def test_stream() -> StreamingResponse:
    task_id = uuid.uuid4().hex
    cancel_event = registry.register(task_id)

    async def generate() -> AsyncIterator[bytes]:
        try:
            async for event in event_sequence(task_id, cancel_event):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
        finally:
            registry.discard(task_id)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, object]:
    if not registry.request_cancel(task_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或已结束",
        )
    return {"cancelled": True, "task_id": task_id}
