from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.container import container

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    database = "ok"
    try:
        assert container.session_factory is not None
        async with asyncio.timeout(10), container.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("healthz database probe failed", exc_info=True)
        database = "unavailable"
    return {"status": "ok", "database": database}
