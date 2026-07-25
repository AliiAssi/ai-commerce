from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.application.dtos.ai_dto import ChatStreamHandle
from app.application.iservices.iai_gateway import IAIGateway
from app.core.config import Settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)
_UNAVAILABLE = "The assistant is unavailable right now — please try again in a moment."


def _error_frame(message: str) -> bytes:
    return f"data: {json.dumps({'type': 'error', 'message': message})}\n\n".encode()


class AIGateway(IAIGateway):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._url = settings.AI_SERVICE_URL.rstrip("/")
        self._key = settings.INTERNAL_API_KEY
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT)

    async def open_chat(
        self, message: str, session_id: str | None, user_email: str | None
    ) -> ChatStreamHandle:
        request = self._client.build_request(
            "POST",
            f"{self._url}/chat",
            headers={"X-Internal-Key": self._key, "Accept": "text/event-stream"},
            json={"message": message, "session_id": session_id, "user_email": user_email},
        )
        try:
            # stream=True so the X-Session-Id header is available before the body arrives.
            response = await self._client.send(request, stream=True)
        except httpx.HTTPError:
            logger.warning("AI service unreachable", exc_info=True)
            return self._failed()

        if response.status_code != 200:
            await response.aread()
            await response.aclose()
            logger.warning("AI service returned HTTP %s", response.status_code)
            return self._failed()

        return ChatStreamHandle(
            session_id=response.headers.get("x-session-id") or None,
            frames=_proxy(response),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _failed(self) -> ChatStreamHandle:
        return ChatStreamHandle(session_id=None, frames=_single_frame(_error_frame(_UNAVAILABLE)))


async def _proxy(response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    except httpx.HTTPError:
        logger.warning("AI stream interrupted", exc_info=True)
        yield _error_frame(_UNAVAILABLE)
    finally:
        await response.aclose()


async def _single_frame(frame: bytes) -> AsyncIterator[bytes]:
    yield frame
