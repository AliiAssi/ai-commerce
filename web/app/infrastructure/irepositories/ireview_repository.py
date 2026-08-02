from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from app.application.dtos.review_dto import ReviewDTO


class IReviewRepository(ABC):
    @abstractmethod
    async def create(self, product_id: int, user_id: int, rating: int, text: str) -> ReviewDTO: ...

    @abstractmethod
    async def list_by_product(self, product_id: int) -> list[ReviewDTO]: ...

    @abstractmethod
    async def exists(self, product_id: int, user_id: int) -> bool: ...

    @abstractmethod
    async def get_by_user(self, product_id: int, user_id: int) -> ReviewDTO | None: ...

    @abstractmethod
    async def rating_stats(self, product_id: int) -> tuple[Decimal, int]: ...
