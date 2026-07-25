from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.application.iservices.iorder_service import IOrderService
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.container import Injected
from app.presentation.flash import flash_redirect
from app.presentation.templates import render

router = APIRouter(prefix="/account")


@router.get("/orders")
async def order_list(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
):
    items = await orders.list_orders(user.id)
    return render(request, "pages/account/orders.html", {"orders": items}, user=user)


@router.get("/orders/{order_id}")
async def order_detail(
    request: Request,
    order_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
):
    order = await orders.get_order(user.id, order_id)
    return render(request, "pages/account/order_detail.html", {"order": order}, user=user)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
):
    await orders.cancel(user.id, order_id)
    return flash_redirect(
        f"/account/orders/{order_id}", "Order cancelled and stock restored.", "success"
    )
