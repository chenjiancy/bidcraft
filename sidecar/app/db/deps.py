"""FastAPI 数据库会话依赖。

sidecar 单进程：engine 在首次请求时惰性创建并复用；
测试通过 reset_engine() 在用例间重建以适配临时数据根。
"""

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.session import make_engine, session_factory

_engine: Engine | None = None


def get_engine() -> Engine:
    """惰性创建并缓存引擎（单进程复用）。"""
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def reset_engine() -> None:
    """测试用：释放并清除缓存引擎，使下次 get_engine 读入新数据根。"""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：出错回滚，最终关闭。"""
    session = session_factory(get_engine())()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
