from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

SortOption = Literal["newest", "price_asc", "price_desc", "rating"]


class CategoryDTO(BaseModel):
    id: int
    name: str
    slug: str
    product_count: int = 0


class ProductDTO(BaseModel):
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


class ProductListDTO(BaseModel):
    items: list[ProductDTO]
    total: int
    page: int
    page_size: int


class ProductSearchParams(BaseModel):
    q: str | None = None
    category_slug: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    sort: SortOption = "newest"
    page: int = 1
    page_size: int = 12
    include_archived: bool = False
    archived_only: bool = False
    max_stock: int | None = None


class ProductStockDTO(BaseModel):
    id: int
    name: str
    price: Decimal
    stock: int
    is_archived: bool


class ProductCreateDTO(BaseModel):
    name: str
    description: str
    origin: str | None = None
    price: Decimal
    stock: int
    category_id: int
    image_url: str | None = None


class ProductUpdateDTO(BaseModel):
    name: str | None = None
    description: str | None = None
    origin: str | None = None
    price: Decimal | None = None
    category_id: int | None = None
    image_url: str | None = None
