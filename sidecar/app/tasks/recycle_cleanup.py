"""回收站定时清理任务：每小时扫描 purge_at <= now 的条目并物理删除。

- 使用简单后台线程 + time.sleep 调度（无额外依赖）
- 保留天数从 config_kv（system.recycle.retention_days）读取，默认 30
- 清理时跳过已在清理中的条目（status=restoring/conflict）
"""

import logging
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.deps import get_engine
from app.models.config_kv import ConfigKV
from app.models.recycle_bin import RecycleBin
from app.repositories.recycle_bin import RecycleBinRepository

logger = logging.getLogger(__name__)


def _get_retention_days(session) -> int:
    """从 config_kv 读取保留天数，默认 30。"""
    row = session.execute(
        select(ConfigKV)
        .where(ConfigKV.scope == "system")
        .where(ConfigKV.key == "recycle.retention_days")
    ).scalar_one_or_none()
    if row is not None and row.value is not None:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            pass
    return 30


def _purge_expired(session) -> int:
    """物理清除过期条目，返回清除数量。"""
    now = datetime.now(UTC)
    stmt = (
        select(RecycleBin)
        .where(RecycleBin.purge_at <= now)
        .where(RecycleBin.status.notin_(("restoring", "conflict")))
    )
    items = list(session.execute(stmt).scalars().all())
    if not items:
        return 0

    bin_repo = RecycleBinRepository(session)
    purged = 0
    for item in items:
        result = bin_repo.purge(item.id)
        if result.get("purged"):
            purged += 1
        else:
            logger.warning("清理回收站条目 %s 失败: %s", item.id, result.get("error"))
    return purged


def _run_cleanup_loop(interval_seconds: int = 3600) -> None:
    """后台清理循环。"""
    while True:
        try:
            engine = get_engine()
            from app.db.session import session_factory

            sess = session_factory(engine)()
            try:
                _purge_expired(sess)
            finally:
                sess.close()
        except Exception:
            logger.exception("回收站定时清理出错")
        time.sleep(interval_seconds)


# 模块级别启动标志（供 test 注入）
_thread: threading.Thread | None = None


def start_cleanup_scheduler(interval_seconds: int = 3600) -> None:
    """启动后台清理线程（幂等）。"""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _thread = threading.Thread(
        target=_run_cleanup_loop,
        args=(interval_seconds,),
        daemon=True,
        name="recycle-bin-cleanup",
    )
    _thread.start()
    logger.info("回收站清理调度器已启动，间隔=%ds", interval_seconds)


def stop_cleanup_scheduler() -> None:
    """停止后台清理线程（测试用）。"""
    global _thread
    _thread = None
