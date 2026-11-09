from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, computed_field

from app.core.links import category_ref, order_ref, product_ref


class CategoryReadDTO(BaseModel):
    id: int
    name: str
    slug: str
    product_count: int

    @computed_field
    @property
    def ref(self) -> str:
        return category_ref(self.slug)


class ProductReadDTO(BaseModel):
    id: int
    name: str
    description: str
    origin: str | None
    price: Decimal
    stock: int
    category: str
    category_slug: str
    image_url: str | None
    rating_avg: Decimal
    review_count: int
    created_at: datetime

    @computed_field
    @property
    def ref(self) -> str:
        return product_ref(self.id)


class ProductPageDTO(BaseModel):
    items: list[ProductReadDTO]
    total: int
    page: int
    page_size: int


class OrderItemReadDTO(BaseModel):
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int


class OrderReadDTO(BaseModel):
    id: int
    user_email: str
    status: str
    total: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemReadDTO]

    @computed_field
    @property
    def ref(self) -> str:
        return order_ref(self.id)


class ReviewReadDTO(BaseModel):
    rating: int
    text: str
    created_at: datetime


class CategoryProductCountDTO(BaseModel):
    name: str
    slug: str
    product_count: int

    @computed_field
    @property
    def ref(self) -> str:
        return category_ref(self.slug)


class StoreStatsDTO(BaseModel):
    product_count: int
    category_count: int
    price_min: Decimal | None
    price_max: Decimal | None
    price_avg: Decimal | None
    top_categories: list[CategoryProductCountDTO]
