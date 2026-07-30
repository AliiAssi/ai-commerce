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

# Two retries at most, and both short. §14.1 gives embedding and reranking a shared 3 s deadline
# and forbids retries from multiplying the request past it: with EMBEDDING_TIMEOUT_SECONDS at
# 2.0, three attempts plus these delays is already the whole budget, which is why a third retry
# is not on offer. The index worker has its own, much longer backoff for the same failures.
_BACKOFF_SECONDS = (0.25, 0.75)


class CircuitBreaker:
    """One provider's failure state, shared across every call to it.

    §12 requires repeated provider failures to have a circuit breaker so that "every query is not
    forced to wait for the same timeout", and requires each circuit to probe recovery and close
    automatically. Both halves matter: without the first, a revoked key costs every shopper
    2 seconds; without the second, recovery needs a deploy.

    There are three states and no explicit half-open flag. While the circuit is open, the first
    call after the reset interval is simply let through — if it succeeds the circuit closes, and
    if it fails the clock restarts. A boolean would add a state to reason about and buy nothing.
    """

    def __init__(self, *, threshold: int, reset_seconds: float, name: str) -> None:
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._name = name
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        # Monotonic, not wall clock: a clock adjustment must not hold a circuit open for hours
        # or close it early. Past the reset interval the circuit reports closed, which is what
        # lets exactly one call through to probe recovery.
        return time.monotonic() - self._opened_at < self._reset_seconds

    def record_success(self) -> None:
        if self._opened_at is not None:
            logger.info("embedding circuit closed for %s", self._name)
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold and self._opened_at is None:
            logger.warning(
                "embedding circuit opened for %s after %d consecutive failures; "
                "search degrades to lexical until it recovers",
                self._name,
                self._failures,
            )
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()


class ResilientEmbeddingClient(IEmbeddingClient):
    """One provider behind a timeout, a bounded retry, and a circuit breaker.

    A decorator over the interface, like `ResilientLLMClient` beside it, and deliberately not an
    extension of it: that class wraps `ILLMClient`, whose failure type, retry contract and
    timeout budget are all different, and it has no breaker at all. What the two share is the
    shape — the caller cannot tell it is not talking to the adapter.

    This wraps *one* provider. Failover between providers is not here and cannot be: vectors from
    two models are not comparable, so a fallback is a different column rather than a different
    call, and the choice of column belongs to the caller that knows which one it is reading.
    """

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
        """Whether the circuit is currently refusing calls, for reporting rather than control."""
        return self._breaker.is_open

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        return await self._call(lambda: self._inner.embed_documents(texts))

    async def embed_query(self, text: str) -> EmbeddingBatch:
        return await self._call(lambda: self._inner.embed_query(text))

    async def _call(self, operation) -> EmbeddingBatch:
        if self._breaker.is_open:
            # Refused without touching the network, which is the entire point: an open circuit
            # that still paid the timeout would leave §12's requirement unmet.
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
        # A non-retryable code counts once, not once per attempt it never made. Otherwise a
        # single revoked-key response would trip a threshold of 3 on its own and the threshold
        # would mean nothing.
        self._breaker.record_failure()
        raise last
