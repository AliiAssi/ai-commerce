from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request

from app.application.dtos.cart_dto import CartDTO
from app.application.iservices.icart_service import ICartService
from app.core.auth import AuthenticatedUser, get_current_user, get_optional_user
from app.core.container import Injected
from app.presentation.templates import render, templates

router = APIRouter(prefix="/cart")


def _cart_fragment(request: Request, cart: CartDTO, message: str):
    return templates.TemplateResponse(
        request,
        "partials/cart_items.html",
        {"cart": cart, "toast_message": message, "with_badge": True},
    )


@router.get("")
async def cart_page(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
):
    cart = await carts.get_cart(user.id)
    return render(
        request,
        "pages/cart.html",
        {"cart": cart, "toast_message": None, "with_badge": False},
        user=user,
    )


@router.get("/badge")
async def cart_badge(
    request: Request,
    user: AuthenticatedUser | None = Depends(get_optional_user),
    carts: ICartService = Injected(ICartService),
):
    count = (await carts.get_cart(user.id)).total_quantity if user else 0
    return templates.TemplateResponse(
        request, "components/cart_badge.html", {"count": count, "oob": False}
    )


@router.post("/items")
async def add_item(
    request: Request,
    product_id: int = Form(),
    quantity: int = Form(default=1, ge=1, le=999),
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
):
    cart = await carts.add_item(user.id, product_id, quantity)
    return _cart_fragment(request, cart, "Added to cart")


@router.post("/items/{product_id}")
async def update_item(
    request: Request,
    product_id: int,
    quantity: int = Form(ge=1, le=999),
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
):
    cart = await carts.update_item(user.id, product_id, quantity)
    return _cart_fragment(request, cart, "Cart updated")


@router.post("/items/{product_id}/remove")
async def remove_item(
    request: Request,
    product_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
):
    cart = await carts.remove_item(user.id, product_id)
    return _cart_fragment(request, cart, "Item removed")
