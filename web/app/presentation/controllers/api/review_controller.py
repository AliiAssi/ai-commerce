from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.iservices.ireview_service import IReviewService
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.container import Injected
from app.presentation.schemas.review_schemas import CreateReviewRequest, ReviewResponse

router = APIRouter(tags=["reviews"])


@router.post("/products/{product_id}/reviews", response_model=ReviewResponse, status_code=201)
async def create_review(
    product_id: int,
    body: CreateReviewRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    reviews: IReviewService = Injected(IReviewService),
) -> ReviewResponse:
    return ReviewResponse.from_dto(
        await reviews.create(user.id, product_id, body.rating, body.text)
    )


@router.get("/products/{product_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    product_id: int,
    reviews: IReviewService = Injected(IReviewService),
) -> list[ReviewResponse]:
    return [ReviewResponse.from_dto(dto) for dto in await reviews.list_for_product(product_id)]
