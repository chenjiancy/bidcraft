"""Alembic 环境。URL 来自 BIDCRAFT_DATA_ROOT（app.db.session.database_url）。"""

from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 导入全部模型以填充 metadata
from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import database_url

config = context.config
_url = database_url()
config.set_main_option("sqlalchemy.url", _url)
if _url.startswith("sqlite:///") and _url.removeprefix("sqlite:///") != ":memory:":
    Path(_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
