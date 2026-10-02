from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence

from app.application.dtos.search_dto import SearchIntent
from app.application.rerank.ireranker import IReranker, RerankCandidate, RerankResult

logger = logging.getLogger(__name__)


def rerank_cache_key(
    version: str, query: str, candidates: Sequence[RerankCandidate], *, window: int
) -> str:
    digest = hashlib.sha256()
    for part in (version, query, str(window)):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1f")
    for candidate in candidates:
        digest.update(str(candidate.product_id).encode("utf-8"))
        digest.update(b"\x1e")
        digest.update(candidate.document_text.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()


class CachedReranker(IReranker):
    def __init__(
        self,
        inner: IReranker,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, RerankResult]] = OrderedDict()

    @property
    def version(self) -> str:
        return self._inner.version

    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult:
        query = intent.semantic_text or intent.normalized_query
        key = rerank_cache_key(self._inner.version, query, candidates, window=window)

        cached = self._get(key)
        if cached is not None:
            logger.info(
                "rerank CACHE HIT q=%r version=%s candidates=%d key=%s",
                intent.original_query,
                cached.version,
                len(candidates),
                key[:12],
            )
            return _copy(cached)

        result = await self._inner.rerank(intent, candidates, window=window)
        if result.applied:
            self._put(key, result)
        return result

    def _get(self, key: str) -> RerankResult | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if self._clock() >= expires_at:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return result

    def _put(self, key: str, result: RerankResult) -> None:
        self._entries[key] = (self._clock() + self._ttl, _copy(result))
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


def _copy(result: RerankResult) -> RerankResult:
    return RerankResult(
        result.product_ids,
        outcome=result.outcome,
        version=result.version,
        scores=result.scores,
    )
