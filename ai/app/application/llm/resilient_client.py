from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.application.llm.illm_client import ILLMClient
from app.application.llm.llm_dtos import LLMMessageDTO, LLMReplyDTO, LLMStreamEventDTO
from app.core.config import Settings
from app.core.exceptions import LLMUnavailableError

logger = logging.getLogger(__name__)

_BACKOFF_SECONDS = (0.5, 2.0)


# Wraps any ILLMClient with timeout + retry-with-backoff, so no provider reimplements it.
# Only retries transient failures, and for streams only before the first event is
# yielded — a partial stream can't be safely restarted.
class ResilientLLMClient(ILLMClient):
    def __init__(self, inner: ILLMClient, settings: Settings) -> None:
        self._inner = inner
        self._timeout = settings.LLM_TIMEOUT_SECONDS
        self._max_attempts = 1 + len(_BACKOFF_SECONDS)

    async def chat(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> LLMReplyDTO:
        for attempt in range(self._max_attempts):
            try:
                async with asyncio.timeout(self._timeout):
                    return await self._inner.chat(messages, tools)
            except (LLMUnavailableError, TimeoutError) as exc:
                await self._maybe_retry(exc, attempt)
        raise LLMUnavailableError("Ollama Cloud unavailable")  # unreachable

    async def stream(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMStreamEventDTO]:
        for attempt in range(self._max_attempts):
            yielded = False
            try:
                async for event in self._inner.stream(messages, tools):
                    yielded = True
                    yield event
                return
            except (LLMUnavailableError, TimeoutError) as exc:
                # Tokens already reached the caller, so the stream can't be restarted.
                if yielded:
                    raise _as_unavailable(exc) from exc
                await self._maybe_retry(exc, attempt)

    async def _maybe_retry(self, exc: Exception, attempt: int) -> None:
        retryable = isinstance(exc, TimeoutError) or (
            isinstance(exc, LLMUnavailableError) and exc.retryable
        )
        if not retryable or attempt >= self._max_attempts - 1:
            raise _as_unavailable(exc) from exc
        delay = _BACKOFF_SECONDS[attempt]
        logger.warning("LLM call failed (%s); retrying in %.1fs", exc, delay)
        await asyncio.sleep(delay)


def _as_unavailable(exc: Exception) -> LLMUnavailableError:
    if isinstance(exc, LLMUnavailableError):
        return exc
    return LLMUnavailableError("Ollama Cloud timed out", retryable=True)
