from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from app.application.dtos.order_dto import (
    AdminOrderPageDTO,
    OrderDTO,
    OrderItemCreateDTO,
    OrderSearchParams,
    OrderStatus,
)


class IOrderRepository(ABC):
    @abstractmethod
    async def create(
        self,
        user_id: int,
        items: list[OrderItemCreateDTO],
        total: Decimal,
        status: OrderStatus = OrderStatus.PAID,
    ) -> OrderDTO: ...

    @abstractmethod
    async def get(self, order_id: int) -> OrderDTO | None: ...

    # Row-locked, for status transitions.
    @abstractmethod
    async def get_for_update(self, order_id: int) -> OrderDTO | None: ...

    @abstractmethod
    async def list_by_user(self, user_id: int) -> list[OrderDTO]: ...

    @abstractmethod
    async def search_all(self, params: OrderSearchParams) -> AdminOrderPageDTO: ...

    @abstractmethod
    async def counts_by_status(self) -> dict[str, int]: ...

    @abstractmethod
    async def revenue_total(self) -> Decimal: ...

    @abstractmethod
    async def set_status(self, order_id: int, status: OrderStatus) -> None: ...

    @abstractmethod
    async def user_purchased_product(self, user_id: int, product_id: int) -> bool: ...

    @abstractmethod
    async def user_has_orders(self, user_id: int) -> bool: ...
