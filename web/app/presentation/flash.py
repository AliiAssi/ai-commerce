from __future__ import annotations

import json
from urllib.parse import quote, unquote

from fastapi import Request
from fastapi.responses import RedirectResponse


def flash_redirect(url: str, message: str, variant: str = "success") -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    payload = quote(json.dumps({"message": message, "variant": variant}))
    response.set_cookie("flash", payload, max_age=15, httponly=True, samesite="lax", path="/")
    return response


def pop_flash(request: Request) -> dict | None:
    raw = request.cookies.get("flash")
    if not raw:
        return None
    try:
        data = json.loads(unquote(raw))
        return {"message": str(data["message"]), "variant": str(data.get("variant", "success"))}
    except (ValueError, KeyError, TypeError):
        return None
