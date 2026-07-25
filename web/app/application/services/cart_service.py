from __future__ import annotations

from app.application.dtos.cart_dto import CartDTO
from app.application.iservices.icart_service import ICartService
from app.core.exceptions import NotFoundError, OutOfStockError
from app.infrastructure.irepositories.icart_repository import ICartRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository


class CartService(ICartService):
    def __init__(self, carts: ICartRepository, products: IProductRepository) -> None:
        self._carts = carts
        self._products = products

    async def get_cart(self, user_id: int) -> CartDTO:
        return await self._carts.get_or_create(user_id)

    async def add_item(self, user_id: int, product_id: int, quantity: int) -> CartDTO:
        product = await self._products.get(product_id)
        if product is None or product.is_archived:
            raise NotFoundError("Product not found")
        if product.stock == 0:
            raise OutOfStockError(f"'{product.name}' is out of stock")
        cart = await self._carts.get_or_create(user_id)
        existing = next((item.quantity for item in cart.items if item.product_id == product_id), 0)
        requested = existing + quantity
        if requested > product.stock:
            raise OutOfStockError(
                f"Only {product.stock} of '{product.name}' available",
                details={
                    "product_id": product_id,
                    "available": product.stock,
                    "requested": requested,
                },
            )
        await self._carts.upsert_item(cart.id, product_id, requested)
        return await self._refreshed(user_id)

    async def update_item(self, user_id: int, product_id: int, quantity: int) -> CartDTO:
        cart = await self._carts.get_by_user(user_id)
        if cart is None or all(item.product_id != product_id for item in cart.items):
            raise NotFoundError("Item not in cart")
        product = await self._products.get(product_id)
        if product is None or product.is_archived:
            raise NotFoundError("Product not found")
        if quantity > product.stock:
            raise OutOfStockError(
                f"Only {product.stock} of '{product.name}' available",
                details={
                    "product_id": product_id,
                    "available": product.stock,
                    "requested": quantity,
                },
            )
        await self._carts.upsert_item(cart.id, product_id, quantity)
        return await self._refreshed(user_id)

    async def remove_item(self, user_id: int, product_id: int) -> CartDTO:
        cart = await self._carts.get_by_user(user_id)
        if cart is None:
            raise NotFoundError("Item not in cart")
        removed = await self._carts.remove_item(cart.id, product_id)
        if not removed:
            raise NotFoundError("Item not in cart")
        return await self._refreshed(user_id)

    async def _refreshed(self, user_id: int) -> CartDTO:
        cart = await self._carts.get_by_user(user_id)
        assert cart is not None
        return cart
