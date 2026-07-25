from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.auth import AuthenticatedUser, get_optional_user
from app.presentation.templates import render

router = APIRouter()


@router.get("/makers")
async def makers(
    request: Request,
    user: AuthenticatedUser | None = Depends(get_optional_user),
):
    return render(request, "pages/static/makers.html", user=user)


@router.get("/about")
async def about(
    request: Request,
    user: AuthenticatedUser | None = Depends(get_optional_user),
):
    return render(request, "pages/static/about.html", user=user)


@router.get("/shipping")
async def shipping(
    request: Request,
    user: AuthenticatedUser | None = Depends(get_optional_user),
):
    return render(request, "pages/static/shipping.html", user=user)
