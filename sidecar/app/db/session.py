"""数据库引擎与会话工厂。

数据库文件位于数据根目录 bidcraft.db；每次调用读取环境变量，
便于测试与 Alembic 在不同数据根间切换。
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import config


def database_url() -> str:
    db_path = Path(config.resolve_data_root()) / "bidcraft.db"
    # Windows 绝对路径 → sqlite:///E:/...（三斜杠 + 绝对路径）
    return f"sqlite:///{db_path.as_posix()}"


def make_engine(url: str | None = None) -> Engine:
    resolved = url or database_url()
    if resolved.startswith("sqlite:///"):
        path_part = resolved.removeprefix("sqlite:///")
        if path_part not in (":memory:", ""):
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(resolved, future=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def iter_session(engine: Engine) -> Iterator[Session]:
    """FastAPI 依赖风格：出错回滚，最终关闭。"""
    session = session_factory(engine)()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
