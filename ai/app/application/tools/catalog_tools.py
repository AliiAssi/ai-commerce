from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.application.dtos.search_params import ProductSearchParams
from app.application.dtos.tool_dto import EmptyParams, ToolSpec
from app.application.tools.registry import ToolRegistry
from app.core.container import Scope
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository


class GetProductParams(BaseModel):
    product_id: int = Field(description="The product's numeric id.")


async def _search_products(params: ProductSearchParams, scope: Scope) -> dict[str, Any]:
    repo = scope.resolve(IProductReadRepository)
    page = await repo.search(params)
    return page.model_dump(mode="json")


async def _get_product(params: GetProductParams, scope: Scope) -> dict[str, Any]:
    repo = scope.resolve(IProductReadRepository)
    product = await repo.get(params.product_id)
    if product is None:
        return {"error": f"no product with id {params.product_id}"}
    return product.model_dump(mode="json")


async def _list_categories(_: EmptyParams, scope: Scope) -> dict[str, Any]:
    repo = scope.resolve(IProductReadRepository)
    categories = await repo.list_categories()
    return {"categories": [c.model_dump(mode="json") for c in categories]}


def register_catalog_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="search_products",
            description=(
                "Search the store catalog with full-text query, category, price range, "
                "stock, and sort options. Returns a page of matching products with prices "
                "(USD), stock, category, and rating. Use this for any 'find / show me / "
                "cheapest / best' product request."
            ),
            params_model=ProductSearchParams,
        ),
        _search_products,
    )
    registry.register(
        ToolSpec(
            name="get_product",
            description=(
                "Get one product's full details by id: description, price, stock, category, "
                "and rating. Use after search_products when the user asks about a specific item."
            ),
            params_model=GetProductParams,
        ),
        _get_product,
    )
    registry.register(
        ToolSpec(
            name="list_categories",
            description=(
                "List all store categories with their slugs and how many products each has. "
                "Use to orient the shopper or to get a slug for search_products."
            ),
            params_model=EmptyParams,
        ),
        _list_categories,
    )
