from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class ProductCardDTO(BaseModel):
    id: int
    name: str
    price: Decimal
    image_url: str | None
    rating_avg: Decimal
    review_count: int
    stock: int
    url: str


class MoreResultsDTO(BaseModel):
    total: int
    url: str
