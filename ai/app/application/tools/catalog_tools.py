from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.application.dtos.search_dto import ExplicitFilters, SearchQuery
from app.application.dtos.search_params import ProductSearchParams
from app.application.dtos.store_read_dto import ProductPageDTO
from app.application.dtos.tool_dto import EmptyParams, ToolSpec
from app.application.iservices.isearch_service import ISearchService
from app.application.tools.registry import ToolRegistry
from app.core.container import Scope, ScopeFactory
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class GetProductParams(BaseModel):
    product_id: int = Field(description="The product's numeric id.")


async def _fallback_search(params: ProductSearchParams, scopes: ScopeFactory) -> dict[str, Any]:
    async with scopes() as scope:
        page = await scope.resolve(IProductReadRepository).search(params)
    return page.model_dump(mode="json")


def _make_search_products(search: ISearchService | None):
    async def _search_products(params: ProductSearchParams, scopes: ScopeFactory) -> dict[str, Any]:
        if search is None or not params.query:
            return await _fallback_search(params, scopes)

        result = await search.search(
            SearchQuery(
                q=params.query,
                explicit=ExplicitFilters(
                    category_slug=params.category_slug,
                    min_price=_decimal(params.min_price),
                    max_price=_decimal(params.max_price),
                    in_stock_only=params.in_stock_only or None,
                    sort=params.sort,
                ),
                page=params.page,
                page_size=params.page_size,
            )
        )

        async with scopes() as scope:
            items = await scope.resolve(IProductReadRepository).by_ids(result.product_ids)

        page = ProductPageDTO(
            items=items, total=result.total, page=result.page, page_size=result.page_size
        )
        payload = page.model_dump(mode="json")
        payload["search"] = {
            "mode": result.mode,
            "language": result.language,
            "reranked": result.reranked,
            "degraded": result.degraded,
            "degraded_reason": result.degraded_reason,
            "inferred_filters": result.inferred_filters,
        }
        return payload

    return _search_products


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


def register_catalog_tools(registry: ToolRegistry, search: ISearchService | None = None) -> None:
    registry.register(
        ToolSpec(
            name="search_products",
            description=(
                "Search the store catalog. Use this for any 'find / show me / cheapest / "
                "best / do you have' product request.\n"
                "\n"
                "WRITING THE QUERY:\n"
                "- Always write `query` in ENGLISH, even when the shopper wrote in Arabic. "
                "The catalog is in English, and an English query is matched three ways "
                "(meaning, words, and fuzzy spelling) while a non-English one is matched only "
                "by meaning. Reply to the shopper in THEIR language.\n"
                "- Rewrite the shopper's words into a short product description. Drop the "
                "conversation ('hi', 'I am looking for', 'do you sell'), keep the words that "
                "describe the product. 'do you have anything sour I can put in fattoush?' "
                "becomes 'sour ingredient for fattoush'.\n"
                "- Keep it descriptive, not a single keyword. The search ranks on meaning, so "
                "'traditional olive oil soap' works better than 'soap'.\n"
                "- Do NOT guess the product name. Describe what the shopper asked for and let "
                "the search find it. Searching 'pomegranate molasses' when they said 'something "
                "sour' hides every other answer if you guessed wrong.\n"
                "- Never send only stop words, punctuation, or an empty string.\n"
                "\n"
                "USING THE FILTERS:\n"
                "- When the shopper is unambiguous, set the structured fields: `max_price` for "
                "'under $20', `in_stock_only` for 'available now', `category_slug` for a named "
                "category, `sort` for 'cheapest' or 'best rated'. These always win over "
                "anything inferred from the text.\n"
                "- When you are not certain, leave the field unset and keep the words in "
                "`query`. The search infers what it can and tells the shopper what it assumed.\n"
                "- Get a valid `category_slug` from list_categories first; do not invent one.\n"
                "\n"
                "READING THE RESULT: the `search` object reports how the answer was produced. "
                "`inferred_filters` is what was understood from the text \u2014 mention it if it "
                "changes what the shopper sees. If `total` is 0, say so plainly and offer to "
                "widen the search; do not invent products."
            ),
            params_model=ProductSearchParams,
            opens_own_scope=True,
        ),
        _make_search_products(search),
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
