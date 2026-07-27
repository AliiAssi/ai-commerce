from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.application.iservices.iai_gateway import IAIGateway
from app.core.config import load_settings_or_exit
from app.core.container import container
from app.core.logging import RequestContextMiddleware, setup_logging
from app.core.registry import configure
from app.presentation.controllers.api import (
    admin_controller,
    ai_controller,
    auth_controller,
    cart_controller,
    order_controller,
    product_controller,
    review_controller,
)
from app.presentation.error_handlers import register_exception_handlers

logger = logging.getLogger(__name__)


# A pure JSON API. The UI is a separate Next.js app that talks to /api/v1 over HTTP, so there
# are no templates, no static mount, and no server-rendered pages here.
#
# CORS is deliberately absent: the browser only ever talks to the Next.js origin, which calls
# this service server-side. Anything that made the browser call this directly would need CORS
# added — and would also mean the API base URL had leaked to the client.
def create_app() -> FastAPI:
    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await _close_ai_gateway()
        if container.engine is not None:
            await container.engine.dispose()

    app = FastAPI(title="BEIT", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_controller.router)
    api.include_router(product_controller.router)
    api.include_router(cart_controller.router)
    api.include_router(order_controller.router)
    api.include_router(review_controller.router)
    api.include_router(admin_controller.router)
    api.include_router(ai_controller.router)
    app.include_router(api)

    @app.get("/healthz")
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

    return app


# peek(), not resolve() — don't construct a gateway just to close it.
async def _close_ai_gateway() -> None:
    gateway = container.peek(IAIGateway)
    if gateway is not None:
        await gateway.aclose()


app = create_app()
