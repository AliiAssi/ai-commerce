from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator

import httpx

from app.application.dtos.ai_dto import ChatStreamHandle
from app.application.iservices.iai_gateway import IAIGateway
from app.core.config import Settings

logger = logging.getLogger(__name__)

# A spun-down instance has to boot before it answers: allow a slow connect and a slow
# first byte (boot + the AI service's own LLM timeout), then rely on per-chunk reads.
_TIMEOUT = httpx.Timeout(connect=60.0, read=120.0, write=10.0, pool=10.0)
# Warming only has to reach the router to trigger the boot, so it never waits for it.
_WARM_TIMEOUT = httpx.Timeout(5.0)
_WARM_INTERVAL = 30.0
# A platform still bringing the instance up answers with these before the app is live.
_RETRY_STATUSES = frozenset({502, 503, 504})

_UNAVAILABLE = "The assistant is unavailable right now — please try again in a moment."


def _error_frame(message: str) -> bytes:
    return f"data: {json.dumps({'type': 'error', 'message': message})}\n\n".encode()


class AIGateway(IAIGateway):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._url = settings.AI_SERVICE_URL.rstrip("/")
        self._key = settings.INTERNAL_API_KEY
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT)
        self._last_warm = 0.0

    async def open_chat(
        self, message: str, session_id: str | None, user_email: str | None
    ) -> ChatStreamHandle:
        # A cold instance can refuse the connection or answer 502 while it boots, so the
        # first failure is retried once. Safe to retry: no response bytes were consumed.
        for attempt in (1, 2):
            retriable = attempt == 1
            try:
                # stream=True so the X-Session-Id header is available before the body arrives.
                response = await self._client.send(
                    self._chat_request(message, session_id, user_email), stream=True
                )
            except httpx.HTTPError:
                logger.warning("AI service unreachable (attempt %s)", attempt, exc_info=True)
                if retriable:
                    continue
                return self._failed()

            if response.status_code == 200:
                return ChatStreamHandle(
                    session_id=response.headers.get("x-session-id") or None,
                    frames=_proxy(response),
                )

            await response.aread()
            await response.aclose()
            logger.warning(
                "AI service returned HTTP %s (attempt %s)", response.status_code, attempt
            )
            if retriable and response.status_code in _RETRY_STATUSES:
                continue
            return self._failed()

        return self._failed()

    async def warm(self) -> None:
        """Nudge a sleeping AI instance into booting; never waits for it to finish."""
        now = time.monotonic()
        if now - self._last_warm < _WARM_INTERVAL:
            return
        self._last_warm = now
        try:
            await self._client.get(f"{self._url}/healthz", timeout=_WARM_TIMEOUT)
        except httpx.HTTPError:
            # Expected while the instance is still starting — the request already
            # reached the platform, which is all the nudge needs.
            logger.debug("AI warm ping did not complete", exc_info=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _chat_request(
        self, message: str, session_id: str | None, user_email: str | None
    ) -> httpx.Request:
        return self._client.build_request(
            "POST",
            f"{self._url}/chat",
            headers={"X-Internal-Key": self._key, "Accept": "text/event-stream"},
            json={"message": message, "session_id": session_id, "user_email": user_email},
        )

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
