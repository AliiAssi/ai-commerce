from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.application.tools.registry import ToolRegistry
from app.core.auth import MCPAuthMiddleware
from app.core.config import load_settings_or_exit
from app.core.container import container
from app.core.logging import RequestContextMiddleware, setup_logging
from app.core.prompts import PromptLibrary
from app.core.registry import configure
from app.presentation.controllers import chat_controller, health_controller
from app.presentation.error_handlers import register_exception_handlers
from app.presentation.mcp.server import build_mcp_server


def create_app() -> FastAPI:
    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)

    mcp = build_mcp_server(
        container.resolve(ToolRegistry), container.resolve(PromptLibrary), settings
    )

    # Must run for the whole app lifetime even in stateless mode.
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp.session_manager.run():
            yield
        if container.engine is not None:
            await container.engine.dispose()

    app = FastAPI(title="BEIT", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_controller.router)
    app.include_router(chat_controller.router)

    app.mount("/mcp", MCPAuthMiddleware(mcp.streamable_http_app(), settings))
    return app


app = create_app()
