from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import DatabaseSettings
from app.infrastructure.database.session import ping_after_idle

IDLE_SECONDS = 60.0


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def backend_pid(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("select pg_backend_pid()"))).scalar_one()


@pytest.fixture
async def pool():
    settings = DatabaseSettings()
    clock = Clock()
    pooled = create_async_engine(
        settings.sqlalchemy_database_url,
        connect_args=settings.database_connect_args,
        pool_size=1,
        max_overflow=0,
    )
    ping_after_idle(pooled.sync_engine, IDLE_SECONDS, clock)
    admin = create_async_engine(
        settings.sqlalchemy_database_url,
        connect_args=settings.database_connect_args,
        poolclass=NullPool,
    )

    async def kill(pid: int) -> None:
        async with admin.connect() as conn:
            await conn.execute(text("select pg_terminate_backend(:pid, 5000)"), {"pid": pid})

    yield pooled, clock, kill
    await pooled.dispose()
    await admin.dispose()


async def test_an_idle_connection_that_died_is_replaced_before_use(pool):
    pooled, clock, kill = pool
    dead = await backend_pid(pooled)
    await kill(dead)

    clock.now += IDLE_SECONDS + 1

    assert await backend_pid(pooled) != dead


async def test_a_recently_used_connection_is_not_pinged(pool):
    pooled, clock, kill = pool
    dead = await backend_pid(pooled)
    await kill(dead)

    clock.now += IDLE_SECONDS - 1

    with pytest.raises(DBAPIError):
        await backend_pid(pooled)
