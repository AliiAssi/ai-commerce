from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.product_dto import CategoryDTO, ProductDTO


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
