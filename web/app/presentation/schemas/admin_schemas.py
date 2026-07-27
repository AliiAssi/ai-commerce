from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.application.dtos.admin_dto import AdminStatsDTO
from app.application.dtos.audit_dto import AuditLogDTO
from app.application.dtos.order_dto import OrderDTO, OrderStatus
from app.presentation.schemas.order_schemas import OrderItemResponse
from app.presentation.schemas.product_schemas import ProductResponse


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int
    admin_email: str
    action: str
    entity_type: str
    entity_id: int | None
    detail: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: AuditLogDTO) -> AuditLogResponse:
        return cls.model_validate(dto)


# Like OrderResponse, but carries who placed the order. The admin order table and the
# dashboard both need it, and the customer-facing OrderResponse deliberately does not.
class AdminOrderResponse(BaseModel):
    id: int
    user_id: int
    user_email: str | None
    status: OrderStatus
    total: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]

    @classmethod
    def from_dto(cls, dto: OrderDTO) -> AdminOrderResponse:
        return cls(
            id=dto.id,
            user_id=dto.user_id,
            user_email=dto.user_email,
            status=dto.status,
            total=dto.total,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            items=[OrderItemResponse.model_validate(item) for item in dto.items],
        )


class OrderStatusCountsResponse(BaseModel):
    counts: dict[str, int]
    total: int

    # The repository groups by status, so a status with no orders is a missing key rather
    # than a zero. Fill every member in so clients can index the map directly.
    @classmethod
    def from_counts(cls, counts: dict[str, int]) -> OrderStatusCountsResponse:
        filled = {status.value: counts.get(status.value, 0) for status in OrderStatus}
        return cls(counts=filled, total=sum(filled.values()))


class AdminStatsResponse(BaseModel):
    revenue: Decimal
    orders_by_status: dict[str, int]
    orders_total: int
    product_count: int
    active_product_count: int
    customer_count: int
    low_stock: list[ProductResponse]
    recent_orders: list[AdminOrderResponse]
    recent_activity: list[AuditLogResponse]

    @classmethod
    def from_dto(cls, dto: AdminStatsDTO) -> AdminStatsResponse:
        return cls(
            revenue=dto.revenue,
            orders_by_status=dto.orders_by_status,
            orders_total=dto.orders_total,
            product_count=dto.product_count,
            active_product_count=dto.active_product_count,
            customer_count=dto.customer_count,
            low_stock=[ProductResponse.from_dto(item) for item in dto.low_stock],
            recent_orders=[AdminOrderResponse.from_dto(item) for item in dto.recent_orders],
            recent_activity=[AuditLogResponse.from_dto(item) for item in dto.recent_activity],
        )
