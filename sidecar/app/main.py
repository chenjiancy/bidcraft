"""FastAPI 应用入口。"""

from fastapi import FastAPI

from app.api import enterprises, model_config, recycle_bin, test_events

app = FastAPI(title="BidCraft Sidecar", version="0.1.0")

app.include_router(test_events.router)
app.include_router(enterprises.router)
app.include_router(recycle_bin.router)
app.include_router(model_config.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
