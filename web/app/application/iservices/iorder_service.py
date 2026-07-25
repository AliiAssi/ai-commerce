from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.order_dto import OrderDTO


class IOrderService(ABC):
    # Instant fake payment — this is a demo store, not a real checkout integration.
    @abstractmethod
    async def checkout(self, user_id: int) -> OrderDTO: ...

    @abstractmethod
    async def list_orders(self, user_id: int) -> list[OrderDTO]: ...

    @abstractmethod
    async def get_order(self, user_id: int, order_id: int) -> OrderDTO: ...

    @abstractmethod
    async def cancel(self, user_id: int, order_id: int) -> OrderDTO: ...

    @abstractmethod
    async def admin_advance_status(self, admin_id: int, order_id: int) -> OrderDTO: ...
