"""FastAPI 最小入口（Task 1）。"""

from fastapi import FastAPI

app = FastAPI(title="BidCraft Sidecar", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
