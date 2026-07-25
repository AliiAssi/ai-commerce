from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.cart_dto import CartDTO


class AddItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=999)


class UpdateItemRequest(BaseModel):
    quantity: int = Field(ge=1, le=999)


class CartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    available_stock: int
    is_archived: bool
    image_url: str | None


class CartResponse(BaseModel):
    id: int
    items: list[CartItemResponse]
    total_quantity: int
    grand_total: Decimal

    @classmethod
    def from_dto(cls, dto: CartDTO) -> CartResponse:
        return cls(
            id=dto.id,
            items=[CartItemResponse.model_validate(item) for item in dto.items],
            total_quantity=dto.total_quantity,
            grand_total=dto.grand_total,
        )
