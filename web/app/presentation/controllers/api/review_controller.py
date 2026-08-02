from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.iservices.ireview_service import IReviewService
from app.core.auth import AuthenticatedUser, get_current_user, get_optional_user
from app.core.container import Injected
from app.presentation.schemas.review_schemas import (
    CreateReviewRequest,
    ReviewEligibilityResponse,
    ReviewResponse,
)

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


@router.get(
    "/products/{product_id}/reviews/eligibility",
    response_model=ReviewEligibilityResponse,
)
async def review_eligibility(
    product_id: int,
    user: AuthenticatedUser | None = Depends(get_optional_user),
    reviews: IReviewService = Injected(IReviewService),
) -> ReviewEligibilityResponse:
    """Answers whether this caller could review this product, so the UI can stop offering a
    form that `create` would refuse. Optional auth: a signed-out caller gets a reason, not a 401.
    """
    return ReviewEligibilityResponse.from_dto(
        await reviews.eligibility(user.id if user else None, product_id)
    )
