from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.iservices.icart_service import ICartService
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.container import Injected
from app.presentation.schemas.cart_schemas import (
    AddItemRequest,
    CartResponse,
    UpdateItemRequest,
)

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartResponse)
async def get_cart(
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
) -> CartResponse:
    return CartResponse.from_dto(await carts.get_cart(user.id))


@router.post("/items", response_model=CartResponse, status_code=201)
async def add_item(
    body: AddItemRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
) -> CartResponse:
    return CartResponse.from_dto(await carts.add_item(user.id, body.product_id, body.quantity))


@router.patch("/items/{product_id}", response_model=CartResponse)
async def update_item(
    product_id: int,
    body: UpdateItemRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
) -> CartResponse:
    return CartResponse.from_dto(await carts.update_item(user.id, product_id, body.quantity))


@router.delete("/items/{product_id}", response_model=CartResponse)
async def remove_item(
    product_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    carts: ICartService = Injected(ICartService),
) -> CartResponse:
    return CartResponse.from_dto(await carts.remove_item(user.id, product_id))
