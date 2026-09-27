from __future__ import annotations

import asyncio
import logging

from app.core.config import load_settings_or_exit
from app.core.container import Scope, container
from app.core.logging import setup_logging
from app.core.registry import configure
from app.infrastructure.irepositories.iproduct_repository import IProductRepository

logger = logging.getLogger(__name__)


async def run() -> None:
    assert container.session_factory is not None
    async with container.session_factory() as session:
        total, active = await Scope(container, session).resolve(IProductRepository).product_counts()
    logger.info("db keepalive: %d products (%d active)", total, active)


async def _main() -> None:
    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)
    assert container.engine is not None
    try:
        await run()
    finally:
        await container.engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
