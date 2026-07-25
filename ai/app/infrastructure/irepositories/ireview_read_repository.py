from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.store_read_dto import ReviewReadDTO


class IReviewReadRepository(ABC):
    @abstractmethod
    async def list_for_product(self, product_id: int, limit: int) -> list[ReviewReadDTO]: ...
