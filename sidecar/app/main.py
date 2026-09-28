"""FastAPI 应用入口。"""

from fastapi import FastAPI

from app.api import test_events

app = FastAPI(title="BidCraft Sidecar", version="0.1.0")

app.include_router(test_events.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
