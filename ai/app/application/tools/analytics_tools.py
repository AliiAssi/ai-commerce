from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.application.dtos.tool_dto import EmptyParams, ToolSpec
from app.application.tools.registry import ToolRegistry
from app.core.container import Scope
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository


class TopNParams(BaseModel):
    n: int = Field(default=5, ge=1, le=20, description="How many products to return.")


async def _store_stats(_: EmptyParams, scope: Scope) -> dict[str, Any]:
    repo = scope.resolve(IProductReadRepository)
    stats = await repo.stats()
    return stats.model_dump(mode="json")


async def _top_rated_products(params: TopNParams, scope: Scope) -> dict[str, Any]:
    repo = scope.resolve(IProductReadRepository)
    products = await repo.top_rated(params.n)
    return {"products": [p.model_dump(mode="json") for p in products]}


async def _low_stock_products(params: TopNParams, scope: Scope) -> dict[str, Any]:
    repo = scope.resolve(IProductReadRepository)
    products = await repo.low_stock(params.n)
    return {"products": [p.model_dump(mode="json") for p in products]}


def register_analytics_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="store_stats",
            description=(
                "Store overview: total products, category count, price range (min/max/avg USD), "
                "and the largest categories. Use for 'how big is the store / what do you sell'."
            ),
            params_model=EmptyParams,
        ),
        _store_stats,
    )
    registry.register(
        ToolSpec(
            name="top_rated_products",
            description="The n highest-rated products (with reviews). Use for 'best' / 'top' asks.",
            params_model=TopNParams,
        ),
        _top_rated_products,
    )
    registry.register(
        ToolSpec(
            name="low_stock_products",
            description="The n products with the lowest stock. Useful for scarcity questions.",
            params_model=TopNParams,
        ),
        _low_stock_products,
    )
