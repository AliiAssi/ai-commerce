from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.application.dtos.audit_dto import AuditLogDTO
from app.application.dtos.order_dto import OrderDTO
from app.application.dtos.product_dto import ProductDTO


class AdminStatsDTO(BaseModel):
    revenue: Decimal
    orders_by_status: dict[str, int]
    orders_total: int
    product_count: int
    active_product_count: int
    customer_count: int
    low_stock: list[ProductDTO]
    recent_orders: list[OrderDTO]
    recent_activity: list[AuditLogDTO]
