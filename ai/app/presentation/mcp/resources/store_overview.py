from __future__ import annotations

from typing import Any

from app.application.tools.registry import ToolRegistry
from app.core.config import Settings
from app.core.container import open_scope
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository


def register(mcp, registry: ToolRegistry, settings: Settings) -> None:
    @mcp.resource(
        "store://overview",
        name="store_overview",
        description="Store name, categories, price range, and policies.",
        mime_type="application/json",
    )
    async def store_overview() -> dict[str, Any]:
        async with open_scope() as scope:
            repo = scope.resolve(IProductReadRepository)
            stats = await repo.stats()
            categories = await repo.list_categories()
        return {
            "store_name": settings.STORE_NAME,
            "currency": "USD",
            "product_count": stats.product_count,
            "categories": [c.model_dump(mode="json") for c in categories],
            "price_range": {
                "min": str(stats.price_min) if stats.price_min is not None else None,
                "max": str(stats.price_max) if stats.price_max is not None else None,
            },
            "policies": {
                "reviews": "verified purchasers only, one review per product",
                "orders": "instant payment; lifecycle paid -> shipped -> delivered; "
                "cancellation allowed before shipping",
            },
        }
