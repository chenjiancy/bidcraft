"""FastAPI 应用入口。"""

import logging
import sys

from fastapi import FastAPI

from app.api import (
    enterprises,
    material_extract,
    materials,
    model_config,
    parse,
    recycle_bin,
    render,
    template_match,
    templates,
    test_events,
)
from app.db.migrate import run_migrations
from app.tasks.recycle_cleanup import start_cleanup_scheduler

# M20 修复：统一日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

app = FastAPI(title="BidCraft Sidecar", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    # 先建/升级库结构再开始服务；失败直接抛出，避免带空库对外服务
    run_migrations()
    start_cleanup_scheduler()


app.include_router(test_events.router)
app.include_router(enterprises.router)
app.include_router(recycle_bin.router)
app.include_router(model_config.router)
app.include_router(parse.router)
app.include_router(materials.router)
app.include_router(material_extract.router)
app.include_router(templates.router)
app.include_router(template_match.router)
app.include_router(render.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
