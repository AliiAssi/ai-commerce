from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.application.dtos.product_dto import ProductSearchParams
from app.application.iservices.iproduct_service import IProductService
from app.core.auth import AuthenticatedUser, get_optional_user
from app.core.container import Injected
from app.presentation.templates import render

router = APIRouter()


@router.get("/")
async def home(
    request: Request,
    user: AuthenticatedUser | None = Depends(get_optional_user),
    products: IProductService = Injected(IProductService),
):
    categories = await products.list_categories()
    featured = await products.search(ProductSearchParams(sort="rating", page_size=8))
    return render(
        request,
        "pages/home.html",
        {"categories": categories, "featured": featured.items},
        user=user,
    )
