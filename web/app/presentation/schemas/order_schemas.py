from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.application.dtos.order_dto import OrderDTO, OrderStatus


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    total: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]

    @classmethod
    def from_dto(cls, dto: OrderDTO) -> OrderResponse:
        return cls(
            id=dto.id,
            status=dto.status,
            total=dto.total,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            items=[OrderItemResponse.model_validate(item) for item in dto.items],
        )
