from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.application.tools.registry import ToolRegistry
from app.core.config import Settings
from app.core.prompts import PromptLibrary
from app.presentation.mcp.prompts import shopping_assistant
from app.presentation.mcp.resources import store_overview
from app.presentation.mcp.tools import analytics, catalog, orders


def _transport_security(settings: Settings) -> TransportSecuritySettings:
    if settings.ENVIRONMENT == "production":
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.mcp_allowed_hosts,
            allowed_origins=settings.mcp_allowed_origins,
        )
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


def build_mcp_server(registry: ToolRegistry, prompts: PromptLibrary, settings: Settings) -> FastMCP:
    mcp = FastMCP(
        "BEIT",
        instructions=prompts.render("mcp.shopping_assistant", store_name=settings.STORE_NAME),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=_transport_security(settings),
    )
    catalog.register(mcp, registry)
    orders.register(mcp, registry)
    analytics.register(mcp, registry)
    store_overview.register(mcp, registry, settings)
    shopping_assistant.register(mcp, prompts, settings)
    return mcp
