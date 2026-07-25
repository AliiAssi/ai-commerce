from __future__ import annotations

from typing import Any

from app.application.dtos.tool_dto import ToolContext
from app.application.tools.registry import ToolRegistry
from app.presentation.mcp.tools.common import run_tool


def register(mcp, registry: ToolRegistry) -> None:
    async def store_stats() -> dict[str, Any]:
        return await run_tool(registry, "store_stats", {}, ToolContext(source="mcp"))

    async def top_rated_products(n: int = 5) -> dict[str, Any]:
        return await run_tool(registry, "top_rated_products", {"n": n}, ToolContext(source="mcp"))

    async def low_stock_products(n: int = 5) -> dict[str, Any]:
        return await run_tool(registry, "low_stock_products", {"n": n}, ToolContext(source="mcp"))

    for fn in (store_stats, top_rated_products, low_stock_products):
        spec = registry.spec(fn.__name__)
        mcp.add_tool(fn, name=spec.name, description=spec.description)
