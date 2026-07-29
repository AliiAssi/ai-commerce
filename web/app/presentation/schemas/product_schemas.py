from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.product_dto import (
    CategoryDTO,
    DegradedReason,
    ProductDTO,
    ProductListDTO,
    SearchMode,
    SortOption,
)
from app.presentation.schemas.common import Page


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    product_count: int

    @classmethod
    def from_dto(cls, dto: CategoryDTO) -> CategoryResponse:
        return cls.model_validate(dto)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    origin: str | None
    price: Decimal
    stock: int
    image_url: str | None
    rating_avg: Decimal
    review_count: int
    is_archived: bool
    category_id: int
    category_name: str
    category_slug: str
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: ProductDTO) -> ProductResponse:
        return cls.model_validate(dto)


class SearchResponse(BaseModel):
    """§9.2's `search` object. Additive: every existing page field keeps its meaning."""

    model_config = ConfigDict(from_attributes=True)

    query: str
    language: str
    mode: SearchMode
    reranked: bool
    effective_sort: SortOption
    inferred_filters: dict[str, str]
    ignored_inferred: list[str]
    degraded: bool
    degraded_reason: DegradedReason | None


class ProductPage(Page[ProductResponse]):
    """The catalog page plus search metadata.

    A subclass rather than a field on the generic `Page`, so carts, orders and reviews do not
    all grow a `search` object they will never populate.
    """

    search: SearchResponse | None = None

    @classmethod
    def from_dto(cls, result: ProductListDTO) -> ProductPage:
        page = cls.build(
            items=[ProductResponse.from_dto(dto) for dto in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )
        if result.search is not None:
            page.search = SearchResponse.model_validate(result.search)
        return page


class ProductCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    origin: str | None = Field(default=None, max_length=80)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int = Field(ge=0)
    category_id: int
    image_url: str | None = Field(default=None, max_length=500)


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    origin: str | None = Field(default=None, max_length=80)
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    category_id: int | None = None
    image_url: str | None = Field(default=None, max_length=500)


class StockAdjustRequest(BaseModel):
    delta: int
