from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse

from app.core.exceptions import (
    AppError,
    AuthError,
    ForbiddenError,
    NotFoundError,
    error_response,
)
from app.presentation.flash import flash_redirect
from app.presentation.templates import render, templates

logger = logging.getLogger(__name__)


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _page_error(request: Request, exc: AppError) -> Response:
    if isinstance(exc, AuthError):
        target = f"/login?next={quote(request.url.path)}"
        if _is_htmx(request):
            return Response(status_code=401, headers={"HX-Redirect": target})
        return RedirectResponse(target, status_code=303)
    if _is_htmx(request):
        return templates.TemplateResponse(
            request,
            "components/toast.html",
            {"message": exc.message, "variant": "danger"},
            status_code=exc.status_code,
        )
    if isinstance(exc, NotFoundError) and request.method == "GET":
        return render(request, "pages/errors/404.html", status_code=404)
    if isinstance(exc, ForbiddenError) and request.method == "GET":
        return render(request, "pages/errors/403.html", status_code=403)
    back = request.headers.get("referer") or "/"
    return flash_redirect(back, exc.message, "danger")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> Response:
        if _is_api(request):
            headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
            return error_response(exc.status_code, exc.code, exc.message, exc.details, headers)
        return _page_error(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
        if _is_api(request):
            return error_response(422, "validation_error", "Invalid request", exc.errors())
        if _is_htmx(request):
            return templates.TemplateResponse(
                request,
                "components/toast.html",
                {"message": "Invalid input, please check the form", "variant": "danger"},
                status_code=422,
            )
        back = request.headers.get("referer") or "/"
        return flash_redirect(back, "Invalid input, please check the form", "danger")

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> Response:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        if _is_api(request):
            return error_response(500, "internal_error", "Internal server error")
        return render(request, "pages/errors/500.html", status_code=500)
