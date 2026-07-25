from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request

from app.application.iservices.iproduct_service import IProductService
from app.application.iservices.ireview_service import IReviewService
from app.core.auth import AuthenticatedUser, get_current_user, get_optional_user
from app.core.container import Injected
from app.presentation.flash import flash_redirect
from app.presentation.templates import render

router = APIRouter()


@router.get("/products/{product_id}")
async def product_detail(
    request: Request,
    product_id: int,
    user: AuthenticatedUser | None = Depends(get_optional_user),
    products: IProductService = Injected(IProductService),
    reviews: IReviewService = Injected(IReviewService),
):
    product = await products.get(product_id)
    review_items = await reviews.list_for_product(product_id)
    return render(
        request,
        "pages/product_detail.html",
        {"product": product, "reviews": review_items},
        user=user,
    )


@router.post("/products/{product_id}/reviews")
async def create_review(
    product_id: int,
    rating: int = Form(ge=1, le=5),
    text: str = Form(min_length=3, max_length=2000),
    user: AuthenticatedUser = Depends(get_current_user),
    reviews: IReviewService = Injected(IReviewService),
):
    await reviews.create(user.id, product_id, rating, text.strip())
    return flash_redirect(f"/products/{product_id}", "Thanks! Your review was published.")
