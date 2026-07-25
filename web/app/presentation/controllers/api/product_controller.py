from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query

from app.application.dtos.product_dto import ProductSearchParams, SortOption
from app.application.iservices.iproduct_service import IProductService
from app.core.container import Injected
from app.presentation.schemas.common import Page
from app.presentation.schemas.product_schemas import CategoryResponse, ProductResponse

router = APIRouter(tags=["catalog"])


@router.get("/products", response_model=Page[ProductResponse])
async def list_products(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    sort: SortOption = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    products: IProductService = Injected(IProductService),
) -> Page[ProductResponse]:
    params = ProductSearchParams(
        q=q,
        category_slug=category,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    result = await products.search(params)
    return Page[ProductResponse].build(
        items=[ProductResponse.from_dto(dto) for dto in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


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
