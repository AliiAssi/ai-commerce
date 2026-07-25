from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class CartItemDTO(BaseModel):
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    available_stock: int
    is_archived: bool
    image_url: str | None


class CartDTO(BaseModel):
    id: int
    user_id: int
    items: list[CartItemDTO]
    total_quantity: int
    grand_total: Decimal
