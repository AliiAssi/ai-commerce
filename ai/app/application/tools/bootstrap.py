from __future__ import annotations

from app.application.events.bus import EventBus
from app.application.iservices.isearch_service import ISearchService
from app.application.tools.analytics_tools import register_analytics_tools
from app.application.tools.catalog_tools import register_catalog_tools
from app.application.tools.order_tools import register_order_tools
from app.application.tools.registry import ScopeFactory, ToolRegistry
from app.core.container import open_scope


def build_tool_registry(
    events: EventBus | None = None,
    scope_factory: ScopeFactory = open_scope,
    search: ISearchService | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(events, scope_factory)
    register_catalog_tools(registry, search)
    register_order_tools(registry)
    register_analytics_tools(registry)
    return registry
