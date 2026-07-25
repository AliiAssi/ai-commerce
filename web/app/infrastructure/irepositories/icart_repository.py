from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.cart_dto import CartDTO


class ICartRepository(ABC):
    @abstractmethod
    async def get_by_user(self, user_id: int) -> CartDTO | None: ...

    @abstractmethod
    async def get_or_create(self, user_id: int) -> CartDTO: ...

    @abstractmethod
    async def upsert_item(self, cart_id: int, product_id: int, quantity: int) -> None: ...

    @abstractmethod
    async def remove_item(self, cart_id: int, product_id: int) -> bool: ...

    @abstractmethod
    async def clear(self, cart_id: int) -> None: ...
