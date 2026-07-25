from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.store_read_dto import ReviewReadDTO
from app.infrastructure.database.store_tables import reviews
from app.infrastructure.irepositories.ireview_read_repository import IReviewReadRepository


class ReviewReadRepository(IReviewReadRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_product(self, product_id: int, limit: int) -> list[ReviewReadDTO]:
        stmt = (
            select(reviews.c.rating, reviews.c.text, reviews.c.created_at)
            .where(reviews.c.product_id == product_id)
            .order_by(reviews.c.created_at.desc(), reviews.c.id.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return [ReviewReadDTO(**row) for row in rows]
