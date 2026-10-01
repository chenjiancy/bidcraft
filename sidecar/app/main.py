"""FastAPI 应用入口。"""

import logging
import os
import sys

# PyInstaller --windowed 且标准句柄未被重定向时（如手动双击 sidecar.exe），
# sys.stdout/stderr 为 None；uvicorn 的 DefaultFormatter 会访问
# sys.stdout.isatty() 而崩溃（onefile 下表现为启动挂死）。
# 正常分发链路由 Electron 以管道方式拉起（句柄有效），此处仅为防御性兜底，
# 保证任何启动方式都不会静默挂死。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

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


# PyInstaller exe 入口（onefile 以 __main__ 执行本文件）。
# dev / 测试经 uvicorn CLI / TestClient 以 app.main:app 导入，不会进入此块。
# 端口由 Electron main 选定后通过 BIDCRAFT_SIDECAR_PORT 注入（与健康检查轮询同口）。
if __name__ == "__main__":
    import uvicorn

    _port = int(os.environ.get("BIDCRAFT_SIDECAR_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=_port, log_level="info")
