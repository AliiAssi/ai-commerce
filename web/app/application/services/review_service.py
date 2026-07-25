from __future__ import annotations

from app.application.dtos.review_dto import ReviewDTO
from app.application.events.bus import EventBus
from app.application.events.definitions import ReviewCreated
from app.application.iservices.ireview_service import IReviewService
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.infrastructure.irepositories.iorder_repository import IOrderRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository
from app.infrastructure.irepositories.ireview_repository import IReviewRepository


class ReviewService(IReviewService):
    def __init__(
        self,
        reviews: IReviewRepository,
        orders: IOrderRepository,
        products: IProductRepository,
        events: EventBus,
    ) -> None:
        self._reviews = reviews
        self._orders = orders
        self._products = products
        self._events = events

    async def create(self, user_id: int, product_id: int, rating: int, text: str) -> ReviewDTO:
        product = await self._products.get(product_id)
        if product is None or product.is_archived:
            raise NotFoundError("Product not found")
        if not await self._orders.user_purchased_product(user_id, product_id):
            raise ForbiddenError("Only verified purchasers can review this product")
        if await self._reviews.exists(product_id, user_id):
            raise ConflictError("You have already reviewed this product")

        review = await self._reviews.create(product_id, user_id, rating, text)
        rating_avg, review_count = await self._reviews.rating_stats(product_id)
        await self._products.update_rating(product_id, rating_avg, review_count)
        self._events.publish(
            ReviewCreated(review_id=review.id, product_id=product_id, user_id=user_id)
        )
        return review

    async def list_for_product(self, product_id: int) -> list[ReviewDTO]:
        product = await self._products.get(product_id)
        if product is None or product.is_archived:
            raise NotFoundError("Product not found")
        return await self._reviews.list_by_product(product_id)
