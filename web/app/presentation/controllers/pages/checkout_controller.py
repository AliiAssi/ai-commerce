from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.application.iservices.icart_service import ICartService
from app.application.iservices.iorder_service import IOrderService
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.container import Injected
from app.presentation.flash import flash_redirect
from app.presentation.templates import render

router = APIRouter()


@router.get("/checkout")
async def checkout_page(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
):
    cart = await carts.get_cart(user.id)
    if not cart.items:
        return flash_redirect("/cart", "Your cart is empty", "warning")
    return render(request, "pages/checkout.html", {"cart": cart}, user=user)


@router.post("/checkout")
async def place_order(
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
):
    order = await orders.checkout(user.id)
    return RedirectResponse(f"/checkout/done/{order.id}", status_code=303)


@router.get("/checkout/done/{order_id}")
async def order_confirmation(
    request: Request,
    order_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    orders: IOrderService = Injected(IOrderService),
):
    order = await orders.get_order(user.id, order_id)
    return render(request, "pages/order_confirmation.html", {"order": order}, user=user)
