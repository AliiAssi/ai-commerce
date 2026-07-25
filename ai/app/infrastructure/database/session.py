from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine_and_sessionmaker(
    settings: Settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        settings.sqlalchemy_database_url,
        connect_args=settings.database_connect_args,
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory
