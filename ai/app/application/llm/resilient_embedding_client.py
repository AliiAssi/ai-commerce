from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from app.application.llm.iembedding_client import (
    ERROR_UNAVAILABLE,
    EmbeddingBatch,
    EmbeddingError,
    IEmbeddingClient,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

_BACKOFF_SECONDS = (0.25, 0.75)


class CircuitBreaker:
    def __init__(
        self, *, threshold: int, reset_seconds: float, name: str, kind: str = "embedding"
    ) -> None:
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._name = name
        self._kind = kind
        self._failures = 0
        self._opened_at: float | None = None
        self._open_seconds = reset_seconds

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        return time.monotonic() - self._opened_at < self._open_seconds

    def record_success(self) -> None:
        if self._opened_at is not None:
            logger.info("%s circuit closed for %s", self._kind, self._name)
        self._failures = 0
        self._opened_at = None
        self._open_seconds = self._reset_seconds

    def record_failure(self, *, trip_immediately: bool = False) -> None:
        self._failures = self._threshold if trip_immediately else self._failures + 1
        if self._failures >= self._threshold and self._opened_at is None:
            logger.warning(
                "%s circuit opened for %s after %d consecutive failures; "
                "search degrades until it recovers",
                self._kind,
                self._name,
                self._failures,
            )
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()

    def open_for(self, seconds: float) -> None:
        self.record_failure(trip_immediately=True)
        self._open_seconds = seconds


class ResilientEmbeddingClient(IEmbeddingClient):
    def __init__(self, inner: IEmbeddingClient, settings: Settings, *, name: str = "") -> None:
        self._inner = inner
        self._timeout = settings.EMBEDDING_TIMEOUT_SECONDS
        self._max_attempts = 1 + len(_BACKOFF_SECONDS)
        self._breaker = CircuitBreaker(
            threshold=settings.EMBEDDING_BREAKER_FAILURES,
            reset_seconds=settings.EMBEDDING_BREAKER_RESET_SECONDS,
            name=name or inner.model,
        )

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    @property
    def is_open(self) -> bool:
        return self._breaker.is_open

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        return await self._call(lambda: self._inner.embed_documents(texts))

    async def embed_query(self, text: str) -> EmbeddingBatch:
        return await self._call(lambda: self._inner.embed_query(text))

    async def _call(self, operation) -> EmbeddingBatch:
        if self._breaker.is_open:
            raise EmbeddingError("embedding circuit is open", code=ERROR_UNAVAILABLE)

        last: EmbeddingError | None = None
        for attempt in range(self._max_attempts):
            try:
                async with asyncio.timeout(self._timeout):
                    batch = await operation()
            except TimeoutError:
                last = EmbeddingError("embedding request timed out", code=ERROR_UNAVAILABLE)
            except EmbeddingError as exc:
                last = exc
            else:
                self._breaker.record_success()
                return batch

            if not last.retryable or attempt >= self._max_attempts - 1:
                break
            await asyncio.sleep(_BACKOFF_SECONDS[attempt])

        assert last is not None
        self._breaker.record_failure()
        raise last
