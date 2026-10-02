from __future__ import annotations

from collections.abc import Sequence

from app.application.dtos.search_dto import SearchIntent
from app.application.rerank.cached_reranker import CachedReranker
from app.application.rerank.ireranker import (
    RERANK_APPLIED,
    RERANK_UNAVAILABLE,
    IReranker,
    RerankCandidate,
    RerankResult,
)

OIL = RerankCandidate(product_id=1, document_text="Name: Koura Olive Oil")
SOAP = RerankCandidate(product_id=2, document_text="Name: Tripoli Olive Oil Soap")


def intent(text: str = "olive oil") -> SearchIntent:
    return SearchIntent(
        original_query=text,
        normalized_query=text,
        semantic_text=text,
        language="en",
        parser_version="test-1",
        lexicon_version=1,
    )


class CountingReranker(IReranker):
    def __init__(self, outcome: str = RERANK_APPLIED) -> None:
        self.calls = 0
        self._outcome = outcome

    @property
    def version(self) -> str:
        return "counting-1"

    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult:
        self.calls += 1
        ids = [candidate.product_id for candidate in reversed(candidates)]
        return RerankResult(
            ids, outcome=self._outcome, version=self.version, scores=[0.9, 0.1][: len(ids)]
        )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def cached(inner: IReranker, *, ttl: float = 60, max_entries: int = 8, clock=None):
    return CachedReranker(inner, ttl_seconds=ttl, max_entries=max_entries, clock=clock or Clock())


class TestTheRerankCache:
    async def test_a_repeated_search_is_served_without_calling_the_provider(self):
        inner = CountingReranker()
        reranker = cached(inner)

        first = await reranker.rerank(intent(), [OIL, SOAP], window=30)
        second = await reranker.rerank(intent(), [OIL, SOAP], window=30)

        assert inner.calls == 1
        assert second.product_ids == first.product_ids == [2, 1]
        assert second.scores == first.scores
        assert second.outcome == RERANK_APPLIED
        assert second.version == "counting-1"

    async def test_a_different_query_is_a_miss(self):
        inner = CountingReranker()
        reranker = cached(inner)

        await reranker.rerank(intent("olive oil"), [OIL, SOAP], window=30)
        await reranker.rerank(intent("soap"), [OIL, SOAP], window=30)

        assert inner.calls == 2

    async def test_an_edited_product_text_is_a_miss(self):
        inner = CountingReranker()
        reranker = cached(inner)
        edited = RerankCandidate(product_id=1, document_text="Name: Koura Olive Oil, 1L")

        await reranker.rerank(intent(), [OIL, SOAP], window=30)
        await reranker.rerank(intent(), [edited, SOAP], window=30)

        assert inner.calls == 2

    async def test_an_unavailable_result_is_not_remembered(self):
        inner = CountingReranker(outcome=RERANK_UNAVAILABLE)
        reranker = cached(inner)

        await reranker.rerank(intent(), [OIL, SOAP], window=30)
        await reranker.rerank(intent(), [OIL, SOAP], window=30)

        assert inner.calls == 2

    async def test_an_entry_expires_after_its_ttl(self):
        inner = CountingReranker()
        clock = Clock()
        reranker = cached(inner, ttl=60, clock=clock)

        await reranker.rerank(intent(), [OIL, SOAP], window=30)
        clock.now = 59
        await reranker.rerank(intent(), [OIL, SOAP], window=30)
        clock.now = 60
        await reranker.rerank(intent(), [OIL, SOAP], window=30)

        assert inner.calls == 2

    async def test_the_least_recently_used_entry_is_evicted_first(self):
        inner = CountingReranker()
        reranker = cached(inner, max_entries=2)

        await reranker.rerank(intent("a"), [OIL, SOAP], window=30)
        await reranker.rerank(intent("b"), [OIL, SOAP], window=30)
        await reranker.rerank(intent("a"), [OIL, SOAP], window=30)
        await reranker.rerank(intent("c"), [OIL, SOAP], window=30)
        assert inner.calls == 3

        await reranker.rerank(intent("a"), [OIL, SOAP], window=30)
        assert inner.calls == 3
        await reranker.rerank(intent("b"), [OIL, SOAP], window=30)
        assert inner.calls == 4

    async def test_changing_a_returned_result_does_not_change_the_cached_one(self):
        reranker = cached(CountingReranker())

        first = await reranker.rerank(intent(), [OIL, SOAP], window=30)
        first.product_ids.append(99)
        second = await reranker.rerank(intent(), [OIL, SOAP], window=30)

        assert second.product_ids == [2, 1]
