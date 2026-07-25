from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
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
from app.presentation.controllers.pages import (
    account_controller as account_pages,
)
from app.presentation.controllers.pages import (
    auth_controller as auth_pages,
)
from app.presentation.controllers.pages import (
    cart_controller as cart_pages,
)
from app.presentation.controllers.pages import (
    catalog_controller as catalog_pages,
)
from app.presentation.controllers.pages import (
    checkout_controller as checkout_pages,
)
from app.presentation.controllers.pages import (
    home_controller as home_pages,
)
from app.presentation.controllers.pages import (
    product_controller as product_pages,
)
from app.presentation.controllers.pages import (
    static_controller as static_pages,
)
from app.presentation.controllers.pages.admin import (
    audit_admin_controller,
    dashboard_controller,
    order_admin_controller,
    product_admin_controller,
)
from app.presentation.error_handlers import register_exception_handlers
from app.presentation.templates import UI_DIR, templates

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)

    templates.env.globals["store_name"] = settings.STORE_NAME
    # The storefront chat widget only renders when the AI service is configured.
    templates.env.globals["ai_enabled"] = bool(
        settings.AI_SERVICE_URL and settings.INTERNAL_API_KEY
    )

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

    pages = APIRouter()
    pages.include_router(home_pages.router)
    pages.include_router(catalog_pages.router)
    pages.include_router(product_pages.router)
    pages.include_router(cart_pages.router)
    pages.include_router(checkout_pages.router)
    pages.include_router(auth_pages.router)
    pages.include_router(account_pages.router)
    pages.include_router(static_pages.router)
    pages.include_router(dashboard_controller.router)
    pages.include_router(product_admin_controller.router)
    pages.include_router(order_admin_controller.router)
    pages.include_router(audit_admin_controller.router)
    app.include_router(pages, include_in_schema=False)

    app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")

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
