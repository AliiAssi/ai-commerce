from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query

from app.application.dtos.product_dto import ProductSearchParams, SortOption
from app.application.iservices.icatalog_search_service import ICatalogSearchService
from app.application.iservices.iproduct_service import IProductService
from app.core.container import Injected, container
from app.presentation.schemas.product_schemas import (
    CategoryResponse,
    ProductPage,
    ProductResponse,
)

router = APIRouter(tags=["catalog"])


# `ignore_inferred` is repeatable *and* comma-separated per §9.1, so `?ignore_inferred=origin`,
# `?ignore_inferred=origin&ignore_inferred=sort` and `?ignore_inferred=origin,sort` all work.
# Unknown names are dropped rather than rejected — a stale bookmark must not 422.
def _ignore_inferred(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    names = [part.strip() for value in values for part in value.split(",") if part.strip()]
    return tuple(dict.fromkeys(names))


# This handler must not use Injected(...): that opens a request-long transaction before the
# body runs, and this path calls the AI service mid-request. ICatalogSearchService takes a
# ScopeFactory instead and opens short scopes around its own queries (§8.2).
@router.get("/products", response_model=ProductPage)
async def list_products(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    origin: str | None = Query(default=None, max_length=100),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    in_stock_only: bool | None = Query(default=None),
    # No default: §9.1 makes the default conditional on `q`, which the DTO resolves.
    sort: SortOption | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    ignore_inferred: list[str] | None = Query(default=None),
) -> ProductPage:
    params = ProductSearchParams(
        q=q,
        category_slug=category,
        origin=origin,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        sort=sort,
        page=page,
        page_size=page_size,
        ignore_inferred=_ignore_inferred(ignore_inferred),
    )
    search = container.resolve(ICatalogSearchService)
    return ProductPage.from_dto(await search.search(params))


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    products: IProductService = Injected(IProductService),
) -> ProductResponse:
    return ProductResponse.from_dto(await products.get(product_id))


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    products: IProductService = Injected(IProductService),
) -> list[CategoryResponse]:
    return [CategoryResponse.from_dto(dto) for dto in await products.list_categories()]
