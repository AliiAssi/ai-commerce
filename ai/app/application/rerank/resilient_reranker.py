from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from app.application.dtos.search_dto import SearchIntent
from app.application.llm.resilient_embedding_client import CircuitBreaker
from app.application.rerank.ireranker import (
    ERROR_QUOTA_EXHAUSTED,
    RERANK_UNAVAILABLE,
    IReranker,
    RerankCandidate,
    RerankError,
    RerankResult,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)


class ResilientReranker(IReranker):
    def __init__(self, inner: IReranker, settings: Settings, *, name: str = "") -> None:
        self._inner = inner
        self._timeout = settings.RERANKER_TIMEOUT_SECONDS
        self._quota_cooldown = settings.RERANKER_QUOTA_COOLDOWN_SECONDS
        self._breaker = CircuitBreaker(
            threshold=settings.RERANKER_BREAKER_FAILURES,
            reset_seconds=settings.RERANKER_BREAKER_RESET_SECONDS,
            name=name or inner.version,
            kind="reranker",
        )

    @property
    def version(self) -> str:
        return self._inner.version

    @property
    def is_open(self) -> bool:
        return self._breaker.is_open

    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult:
        fallback = [candidate.product_id for candidate in candidates]

        if self._breaker.is_open:
            return RerankResult(fallback, outcome=RERANK_UNAVAILABLE, version=self.version)

        try:
            async with asyncio.timeout(self._timeout):
                result = await self._inner.rerank(intent, candidates, window=window)
        except TimeoutError:
            self._breaker.record_failure()
            logger.warning("reranker %s timed out after %.1fs", self.version, self._timeout)
            return RerankResult(fallback, outcome=RERANK_UNAVAILABLE, version=self.version)
        except RerankError as exc:
            if exc.code == ERROR_QUOTA_EXHAUSTED:
                self._breaker.open_for(self._quota_cooldown)
                logger.warning(
                    "reranker %s allowance is exhausted; not reranking for %.0fs",
                    self.version,
                    self._quota_cooldown,
                )
            else:
                self._breaker.record_failure()
                logger.warning("reranker %s failed (%s)", self.version, exc.code)
            return RerankResult(fallback, outcome=RERANK_UNAVAILABLE, version=self.version)

        self._breaker.record_success()
        if len(result.product_ids) != len(fallback):
            logger.warning(
                "reranker %s returned %d of %d candidates; keeping the fused order",
                self.version,
                len(result.product_ids),
                len(fallback),
            )
            return RerankResult(fallback, outcome=RERANK_UNAVAILABLE, version=self.version)
        return result
