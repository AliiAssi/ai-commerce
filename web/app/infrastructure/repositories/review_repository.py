from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.review_dto import ReviewDTO
from app.infrastructure.irepositories.ireview_repository import IReviewRepository
from app.infrastructure.models.review import Review
from app.infrastructure.models.user import User


class ReviewRepository(IReviewRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # Author email is fetched separately (not via a lazy relationship) to keep this async-safe.
    async def create(self, product_id: int, user_id: int, rating: int, text: str) -> ReviewDTO:
        review = Review(product_id=product_id, user_id=user_id, rating=rating, text=text)
        self._session.add(review)
        await self._session.flush()
        await self._session.refresh(review)
        email = await self._session.scalar(select(User.email).where(User.id == user_id))
        return ReviewDTO(
            id=review.id,
            product_id=review.product_id,
            user_id=review.user_id,
            user_email=email or "",
            rating=review.rating,
            text=review.text,
            created_at=review.created_at,
        )

    async def list_by_product(self, product_id: int) -> list[ReviewDTO]:
        reviews = (
            await self._session.scalars(
                select(Review)
                .where(Review.product_id == product_id)
                .order_by(Review.created_at.desc(), Review.id.desc())
            )
        ).all()
        return [
            ReviewDTO(
                id=review.id,
                product_id=review.product_id,
                user_id=review.user_id,
                user_email=review.user.email,
                rating=review.rating,
                text=review.text,
                created_at=review.created_at,
            )
            for review in reviews
        ]

    async def exists(self, product_id: int, user_id: int) -> bool:
        row = await self._session.scalar(
            select(Review.id)
            .where(Review.product_id == product_id, Review.user_id == user_id)
            .limit(1)
        )
        return row is not None

    async def rating_stats(self, product_id: int) -> tuple[Decimal, int]:
        row = (
            await self._session.execute(
                select(
                    func.coalesce(func.avg(Review.rating), 0),
                    func.count(Review.id),
                ).where(Review.product_id == product_id)
            )
        ).one()
        average = Decimal(row[0]).quantize(Decimal("0.01"))
        return average, row[1]
