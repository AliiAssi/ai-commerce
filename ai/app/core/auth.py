from __future__ import annotations

import hmac
import json

from fastapi import Header

from app.core.config import Settings
from app.core.container import container
from app.core.exceptions import AuthError


async def require_internal_key(x_internal_key: str = Header(default="")) -> None:
    settings = container.resolve(Settings)
    if not hmac.compare_digest(x_internal_key, settings.INTERNAL_API_KEY):
        raise AuthError("invalid or missing internal API key")


class MCPAuthMiddleware:
    def __init__(self, app, settings: Settings) -> None:
        self.app = app
        self._expected = f"Bearer {settings.MCP_BEARER_TOKEN}"

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        if not hmac.compare_digest(headers.get("authorization", ""), self._expected):
            await _deny(
                send,
                401,
                "unauthorized",
                "invalid or missing bearer token",
                extra_headers=[(b"www-authenticate", b"Bearer")],
            )
            return

        await self.app(scope, receive, send)


async def _deny(send, status: int, code: str, message: str, extra_headers=None) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        *(extra_headers or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
