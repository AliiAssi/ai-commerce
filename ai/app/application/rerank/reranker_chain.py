from __future__ import annotations

import logging
from collections.abc import Sequence

from app.application.dtos.search_dto import SearchIntent
from app.application.rerank.ireranker import (
    RERANK_UNAVAILABLE,
    IReranker,
    RerankCandidate,
    RerankResult,
)

logger = logging.getLogger(__name__)


class RerankerChain(IReranker):
    def __init__(self, primary: IReranker, fallback: IReranker) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def version(self) -> str:
        return f"{self._primary.version}+{self._fallback.version}"

    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult:
        result = await self._primary.rerank(intent, candidates, window=window)
        if result.outcome != RERANK_UNAVAILABLE:
            return result

        logger.info("reranker %s declined; trying the fallback", self._primary.version)
        second = await self._fallback.rerank(intent, candidates, window=window)
        if second.outcome != RERANK_UNAVAILABLE:
            return second

        return RerankResult(
            [candidate.product_id for candidate in candidates],
            outcome=RERANK_UNAVAILABLE,
            version=self.version,
        )
