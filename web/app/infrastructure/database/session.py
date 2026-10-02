from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry
from sqlalchemy.util import await_only

from app.core.config import Settings

PING_AFTER_IDLE_SECONDS = 60.0
_CHECKED_IN_AT = "checked_in_at"


def create_engine_and_sessionmaker(
    settings: Settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        settings.sqlalchemy_database_url,
        connect_args=settings.database_connect_args,
        pool_size=2,
        max_overflow=3,
    )
    ping_after_idle(engine.sync_engine, PING_AFTER_IDLE_SECONDS)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


def ping_after_idle(
    engine: Engine, idle_seconds: float, clock: Callable[[], float] = time.monotonic
) -> None:
    @event.listens_for(engine, "checkin")
    def _remember_checkin(dbapi_connection: Any, record: ConnectionPoolEntry) -> None:
        record.info[_CHECKED_IN_AT] = clock()

    @event.listens_for(engine, "checkout")
    def _ping_if_idle(dbapi_connection: Any, record: ConnectionPoolEntry, proxy: Any) -> None:
        checked_in_at = record.info.get(_CHECKED_IN_AT)
        if checked_in_at is None or clock() - checked_in_at < idle_seconds:
            return
        try:
            await_only(dbapi_connection.driver_connection.execute("SELECT 1"))
        except Exception as exc:
            raise DisconnectionError("idle connection failed its ping") from exc
