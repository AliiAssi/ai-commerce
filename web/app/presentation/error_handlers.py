from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import AppError, error_response

logger = logging.getLogger(__name__)


# Every route is JSON now, so there is no longer a page branch: no HTML error templates, no
# HX-Redirect for htmx, no flash-cookie redirect back to a referer. The frontend renders its
# own error states from these envelopes.
def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> Response:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return error_response(exc.status_code, exc.code, exc.message, exc.details, headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> Response:
        return error_response(422, "validation_error", "Invalid request", exc.errors())

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> Response:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "Internal server error")
