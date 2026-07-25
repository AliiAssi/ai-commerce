from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.iservices.iorder_service import IOrderService
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.container import Injected
from app.presentation.schemas.order_schemas import OrderResponse

router = APIRouter(tags=["orders"])


@router.post("/checkout", response_model=OrderResponse, status_code=201)
async def checkout(
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
) -> OrderResponse:
    return OrderResponse.from_dto(await orders.checkout(user.id))


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
) -> list[OrderResponse]:
    return [OrderResponse.from_dto(dto) for dto in await orders.list_orders(user.id)]


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
) -> OrderResponse:
    return OrderResponse.from_dto(await orders.get_order(user.id, order_id))


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
) -> OrderResponse:
    return OrderResponse.from_dto(await orders.cancel(user.id, order_id))
