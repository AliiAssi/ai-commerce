from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import AuthenticatedUser
from app.presentation.flash import pop_flash

UI_DIR = Path(__file__).resolve().parents[1] / "ui"

templates = Jinja2Templates(directory=str(UI_DIR / "templates"))


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    user: AuthenticatedUser | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    ctx: dict[str, Any] = {"user": user, "flash": pop_flash(request)}
    ctx.update(context or {})
    response = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    if ctx["flash"] is not None:
        response.delete_cookie("flash", path="/")
    return response
