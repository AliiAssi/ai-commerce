from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response

from app.application.dtos.user_dto import TokenDTO
from app.application.iservices.iauth_service import IAuthService
from app.core.auth import ACCESS_TOKEN_COOKIE, AuthenticatedUser, get_optional_user
from app.core.config import get_settings
from app.core.container import Injected
from app.presentation.templates import render

router = APIRouter()


# Only same-site relative redirect targets are allowed, to avoid open-redirect abuse.
def _safe_next(next_url: str) -> str:
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


def _set_auth_cookie(response: Response, token: TokenDTO) -> None:
    settings = get_settings()
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token.access_token,
        max_age=token.expires_in,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        path="/",
    )


@router.get("/login")
async def login_page(
    request: Request,
    next: str = "/",
    user: AuthenticatedUser | None = Depends(get_optional_user),
):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return render(request, "pages/auth/login.html", {"next": _safe_next(next)})


@router.post("/login")
async def login_submit(
    email: str = Form(),
    password: str = Form(),
    next: str = Form(default="/"),
    auth: IAuthService = Injected(IAuthService),
):
    token = await auth.login(email, password)
    response = RedirectResponse(_safe_next(next), status_code=303)
    _set_auth_cookie(response, token)
    return response


@router.get("/register")
async def register_page(
    request: Request,
    next: str = "/",
    user: AuthenticatedUser | None = Depends(get_optional_user),
):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return render(request, "pages/auth/register.html", {"next": _safe_next(next)})


@router.post("/register")
async def register_submit(
    email: str = Form(),
    password: str = Form(min_length=8, max_length=72),
    next: str = Form(default="/"),
    auth: IAuthService = Injected(IAuthService),
):
    token = await auth.register(email, password)
    response = RedirectResponse(_safe_next(next), status_code=303)
    _set_auth_cookie(response, token)
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    return response
