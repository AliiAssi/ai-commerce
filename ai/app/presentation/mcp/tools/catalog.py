from __future__ import annotations

from typing import Any, Literal

from app.application.dtos.tool_dto import ToolContext
from app.application.tools.registry import ToolRegistry
from app.presentation.mcp.tools.common import run_tool


def register(mcp, registry: ToolRegistry) -> None:
    async def search_products(
        query: str | None = None,
        category_slug: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock_only: bool = False,
        sort: Literal["relevance", "newest", "price_asc", "price_desc", "rating"] = "rating",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        return await run_tool(
            registry,
            "search_products",
            {
                "query": query,
                "category_slug": category_slug,
                "min_price": min_price,
                "max_price": max_price,
                "in_stock_only": in_stock_only,
                "sort": sort,
                "page": page,
                "page_size": page_size,
            },
            ToolContext(source="mcp"),
        )

    async def get_product(product_id: int) -> dict[str, Any]:
        return await run_tool(
            registry, "get_product", {"product_id": product_id}, ToolContext(source="mcp")
        )

    async def list_categories() -> dict[str, Any]:
        return await run_tool(registry, "list_categories", {}, ToolContext(source="mcp"))

    for fn in (search_products, get_product, list_categories):
        spec = registry.spec(fn.__name__)
        mcp.add_tool(fn, name=spec.name, description=spec.description)
