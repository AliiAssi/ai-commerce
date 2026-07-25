from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.application.dtos.tool_dto import ToolSpec
from app.application.tools.registry import ToolRegistry
from app.core.container import Scope
from app.infrastructure.irepositories.iorder_read_repository import IOrderReadRepository

_NOT_SIGNED_IN = {"error": "order lookups need a signed-in customer"}


class GetOrderParams(BaseModel):
    order_id: int = Field(description="The order's numeric id.")
    user_email: str | None = Field(
        default=None, description="Do not set — the signed-in customer is used automatically."
    )


class ListOrdersParams(BaseModel):
    user_email: str | None = Field(
        default=None, description="Do not set — the signed-in customer is used automatically."
    )
    limit: int = Field(default=10, ge=1, le=50, description="Maximum orders to return.")


class GetOrderStatusParams(BaseModel):
    order_id: int = Field(description="The order's numeric id.")
    user_email: str | None = Field(
        default=None, description="Do not set — the signed-in customer is used automatically."
    )


async def _get_order(params: GetOrderParams, scope: Scope) -> dict[str, Any]:
    if not params.user_email:
        return _NOT_SIGNED_IN
    repo = scope.resolve(IOrderReadRepository)
    order = await repo.get(params.order_id, user_email=params.user_email)
    if order is None:
        return {"error": f"no order #{params.order_id} for this customer"}
    return order.model_dump(mode="json")


async def _list_orders(params: ListOrdersParams, scope: Scope) -> dict[str, Any]:
    if not params.user_email:
        return _NOT_SIGNED_IN
    repo = scope.resolve(IOrderReadRepository)
    orders = await repo.list_for_user(params.user_email, params.limit)
    return {"orders": [o.model_dump(mode="json") for o in orders]}


async def _get_order_status(params: GetOrderStatusParams, scope: Scope) -> dict[str, Any]:
    if not params.user_email:
        return _NOT_SIGNED_IN
    repo = scope.resolve(IOrderReadRepository)
    order = await repo.get(params.order_id, user_email=params.user_email)
    if order is None:
        return {"error": f"no order #{params.order_id} for this customer"}
    return {
        "order_id": order.id,
        "status": order.status,
        "updated_at": order.updated_at.isoformat(),
    }


def register_order_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="get_order",
            description=(
                "Get one of the signed-in customer's orders by id: items, totals, status, "
                "and timestamps. Only the current customer's own orders are visible."
            ),
            params_model=GetOrderParams,
            customer_scoped=True,
        ),
        _get_order,
    )
    registry.register(
        ToolSpec(
            name="list_orders",
            description=(
                "List the signed-in customer's recent orders (most recent first) with status "
                "and totals. Use for 'my orders' / 'order history' questions."
            ),
            params_model=ListOrdersParams,
            customer_scoped=True,
        ),
        _list_orders,
    )
    registry.register(
        ToolSpec(
            name="get_order_status",
            description=(
                "Get just the current status (paid, shipped, delivered, cancelled) of one of "
                "the signed-in customer's orders. Use for 'where is my order?' questions."
            ),
            params_model=GetOrderStatusParams,
            customer_scoped=True,
        ),
        _get_order_status,
    )
