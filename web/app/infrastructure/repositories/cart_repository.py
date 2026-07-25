from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.cart_dto import CartDTO, CartItemDTO
from app.infrastructure.irepositories.icart_repository import ICartRepository
from app.infrastructure.models.cart import Cart, CartItem


class CartRepository(ICartRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_dto(cart: Cart) -> CartDTO:
        items = [
            CartItemDTO(
                product_id=item.product_id,
                product_name=item.product.name,
                unit_price=item.product.price,
                quantity=item.quantity,
                line_total=item.product.price * item.quantity,
                available_stock=item.product.stock,
                is_archived=item.product.is_archived,
                image_url=item.product.image_url,
            )
            for item in cart.items
        ]
        return CartDTO(
            id=cart.id,
            user_id=cart.user_id,
            items=items,
            total_quantity=sum(item.quantity for item in items),
            grand_total=sum((item.line_total for item in items), Decimal("0.00")),
        )

    async def get_by_user(self, user_id: int) -> CartDTO | None:
        cart = await self._session.scalar(
            select(Cart).where(Cart.user_id == user_id).execution_options(populate_existing=True)
        )
        return self._to_dto(cart) if cart else None

    async def get_or_create(self, user_id: int) -> CartDTO:
        existing = await self.get_by_user(user_id)
        if existing is not None:
            return existing
        cart = Cart(user_id=user_id)
        self._session.add(cart)
        await self._session.flush()
        return CartDTO(
            id=cart.id,
            user_id=user_id,
            items=[],
            total_quantity=0,
            grand_total=Decimal("0.00"),
        )

    async def upsert_item(self, cart_id: int, product_id: int, quantity: int) -> None:
        item = await self._session.scalar(
            select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
        )
        if item is None:
            self._session.add(CartItem(cart_id=cart_id, product_id=product_id, quantity=quantity))
        else:
            item.quantity = quantity
        await self._session.flush()

    async def remove_item(self, cart_id: int, product_id: int) -> bool:
        result = await self._session.execute(
            delete(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
        )
        return result.rowcount > 0

    async def clear(self, cart_id: int) -> None:
        await self._session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))
