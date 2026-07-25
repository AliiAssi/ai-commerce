from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class OrderStatus(StrEnum):
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItemDTO(BaseModel):
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class OrderItemCreateDTO(BaseModel):
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int


class OrderDTO(BaseModel):
    id: int
    user_id: int
    status: OrderStatus
    total: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemDTO]
    user_email: str | None = None


class OrderSearchParams(BaseModel):
    status: OrderStatus | None = None
    page: int = 1
    page_size: int = 20


class AdminOrderPageDTO(BaseModel):
    items: list[OrderDTO]
    total: int
    page: int
    page_size: int
