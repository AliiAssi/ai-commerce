from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.store_read_dto import OrderReadDTO


class IOrderReadRepository(ABC):
    @abstractmethod
    async def get(self, order_id: int, user_email: str | None = None) -> OrderReadDTO | None: ...

    @abstractmethod
    async def list_for_user(self, user_email: str, limit: int) -> list[OrderReadDTO]: ...
