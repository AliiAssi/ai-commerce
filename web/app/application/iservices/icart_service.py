from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.cart_dto import CartDTO


class ICartService(ABC):
    @abstractmethod
    async def get_cart(self, user_id: int) -> CartDTO: ...

    @abstractmethod
    async def add_item(self, user_id: int, product_id: int, quantity: int) -> CartDTO: ...

    @abstractmethod
    async def update_item(self, user_id: int, product_id: int, quantity: int) -> CartDTO: ...

    @abstractmethod
    async def remove_item(self, user_id: int, product_id: int) -> CartDTO: ...
