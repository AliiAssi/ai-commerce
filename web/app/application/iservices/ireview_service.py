from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.review_dto import ReviewDTO, ReviewEligibilityDTO


class IReviewService(ABC):
    @abstractmethod
    async def create(self, user_id: int, product_id: int, rating: int, text: str) -> ReviewDTO: ...

    @abstractmethod
    async def list_for_product(self, product_id: int) -> list[ReviewDTO]: ...

    @abstractmethod
    async def eligibility(self, user_id: int | None, product_id: int) -> ReviewEligibilityDTO: ...
