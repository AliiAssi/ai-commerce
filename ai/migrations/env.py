from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.infrastructure.models.chat_message
import app.infrastructure.models.chat_session
import app.infrastructure.models.search  # noqa: F401
from app.core.config import get_settings
from app.infrastructure.database.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()

# this service's Alembic only ever manages ai_* tables; web owns the store schema in the
# same database. A separate version table keeps the two migration histories from colliding.
VERSION_TABLE = "ai_alembic_version"


# never autogenerate or touch web-owned tables
def include_object(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table":
        return name.startswith("ai_")
    return True


# emit sql to stdout without a live connection
def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


# run the migration statements on an established connection
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


# connect with the async driver and hand off to the sync runner
async def run_migrations_online() -> None:
    engine = create_async_engine(
        settings.sqlalchemy_database_url,
        connect_args=settings.database_connect_args,
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
