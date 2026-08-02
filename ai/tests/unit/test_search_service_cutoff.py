from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.application.dtos.search_dto import (
    ExplicitFilters,
    QueryVectorDTO,
    RetrievalRequest,
    RetrievalResult,
    SearchIntent,
    SearchQuery,
)
from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.rerank.ireranker import (
    RERANK_APPLIED,
    RERANK_SKIPPED,
    RERANK_UNAVAILABLE,
    IReranker,
    RerankCandidate,
    RerankResult,
)
from app.application.search.parser import IntentParser
from app.application.services.search_service import SearchService
from app.core.config import Settings
from app.core.index_state import IndexCoverage
from app.core.search_aliases import load_aliases
from app.core.vector_schema import EMBEDDING_VECTOR_DIMENSIONS
from app.infrastructure.irepositories.isearch_repository import ISearchRepository

BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "INTERNAL_API_KEY": "x" * 16,
    "MCP_BEARER_TOKEN": "y" * 16,
    "OLLAMA_API_KEY": "dummy",
}


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})


def smart_settings(**overrides) -> Settings:
    return settings(
        SMART_SEARCH_ENABLED=True,
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL="gemini-embedding-001",
        EMBEDDING_DIMENSIONS=EMBEDDING_VECTOR_DIMENSIONS,
        EMBEDDING_API_KEY="a-key",
        **overrides,
    )


class FakeSearchRepository(ISearchRepository):
    def __init__(self, product_ids: Sequence[int], *, total: int | None = None) -> None:
        self.product_ids = list(product_ids)
        self.total = len(self.product_ids) if total is None else total
        self.page = 1
        self.page_size = 12

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        self.page = request.page
        self.page_size = request.page_size
        return RetrievalResult(
            product_ids=self.product_ids,
            total=self.total,
            page=request.page,
            page_size=request.page_size,
            semantic_hits=len(self.product_ids),
            trigram_hits=len(self.product_ids),
            semantic_used=True,
            documents_used=True,
        )

    async def rerank_candidates(self, product_ids: Sequence[int]) -> list[RerankCandidate]:
        return [RerankCandidate(pid, f"product {pid}") for pid in product_ids]

    async def cached_query_vector(self, cache_key: str) -> QueryVectorDTO | None:
        return None

    async def store_query_vector(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def catalog_terms(self):  # pragma: no cover - not exercised here
        raise NotImplementedError

    async def detect_capabilities(self):  # pragma: no cover - not exercised here
        raise NotImplementedError


class StubReranker(IReranker):
    def __init__(self, scores: Sequence[float] | None, *, outcome: str = RERANK_APPLIED) -> None:
        self._scores = scores
        self._outcome = outcome

    @property
    def version(self) -> str:
        return "stub-1"

    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult:
        ids = [candidate.product_id for candidate in candidates]
        if self._scores is None:
            return RerankResult(ids, outcome=self._outcome, version=self.version)
        ranked = sorted(range(len(ids)), key=lambda i: -self._scores[i])
        return RerankResult(
            [ids[i] for i in ranked],
            outcome=self._outcome,
            version=self.version,
            scores=[self._scores[i] for i in ranked],
        )


def build(repository: FakeSearchRepository, reranker: IReranker, config: Settings) -> SearchService:
    aliases = load_aliases()

    @asynccontextmanager
    async def scope_factory() -> AsyncIterator[Any]:
        class _Scope:
            def resolve(self, interface):
                assert interface is ISearchRepository
                return repository

        yield _Scope()

    return SearchService(
        parser=IntentParser(aliases),
        aliases=aliases,
        providers=EmbeddingProviders(primary=None),
        reranker=reranker,
        coverage=IndexCoverage(),
        settings=config,
        scope_factory=scope_factory,
    )


def _price_sort() -> ExplicitFilters:
    return ExplicitFilters(sort="price_asc")


@pytest.fixture
def config():
    return settings(RERANK_MIN_SCORE=0.15, RERANK_GAP_RATIO=0.35, RERANK_MAX_RESULTS=12)


async def test_the_irrelevant_tail_never_reaches_the_caller(config):
    repository = FakeSearchRepository([1, 2, 3, 4, 5])
    service = build(repository, StubReranker([0.91, 0.62, 0.44, 0.02, 0.001]), config)

    result = await service.search(SearchQuery(q="sour ingredient for fattoush"))

    assert result.product_ids == [1, 2, 3]
    assert result.reranked is True


async def test_the_reported_total_matches_what_is_shown(config):
    repository = FakeSearchRepository([1, 2, 3, 4, 5], total=5)
    service = build(repository, StubReranker([0.91, 0.62, 0.44, 0.02, 0.001]), config)

    result = await service.search(SearchQuery(q="sour ingredient for fattoush"))

    assert result.total == 3, "a count of 5 above three cards is its own bug"


async def test_a_deeper_page_counts_the_pages_already_behind_it(config):
    repository = FakeSearchRepository([1, 2, 3, 4], total=40)
    service = build(repository, StubReranker([0.91, 0.62, 0.02, 0.001]), config)

    result = await service.search(SearchQuery(q="olive oil", page=3, page_size=12))

    assert result.total == 26, "two full pages behind it, two kept on it"


async def test_nothing_relevant_returns_nothing(config):
    repository = FakeSearchRepository([1, 2, 3])
    service = build(repository, StubReranker([0.04, 0.02, 0.01]), config)

    result = await service.search(SearchQuery(q="zzzznotathing"))

    assert result.product_ids == []
    assert result.total == 0


async def test_one_strong_match_comes_back_alone(config):
    repository = FakeSearchRepository([1, 2, 3, 4])
    service = build(repository, StubReranker([0.97, 0.21, 0.19, 0.18]), config)

    result = await service.search(SearchQuery(q="Baladi Extra Virgin Olive Oil"))

    assert result.product_ids == [1]


async def test_an_untouched_result_set_keeps_its_pagination(config):
    repository = FakeSearchRepository([1, 2, 3], total=40)
    service = build(repository, StubReranker([0.91, 0.62, 0.44]), config)

    result = await service.search(SearchQuery(q="olive oil"))

    assert result.product_ids == [1, 2, 3]
    assert result.total == 40


async def test_an_unavailable_reranker_serves_the_wide_set_and_says_so():
    repository = FakeSearchRepository([1, 2, 3, 4, 5])
    service = build(repository, StubReranker(None, outcome=RERANK_UNAVAILABLE), smart_settings())

    result = await service.search(SearchQuery(q="sour ingredient for fattoush"))

    assert result.product_ids == [1, 2, 3, 4, 5]
    assert result.degraded is True
    assert result.degraded_reason == "reranker_unavailable"


async def test_an_explicit_sort_is_not_a_degradation():
    repository = FakeSearchRepository([1, 2, 3, 4, 5])
    service = build(repository, StubReranker(None, outcome=RERANK_SKIPPED), smart_settings())

    result = await service.search(SearchQuery(q="olive oil cheapest first"))

    assert result.product_ids == [1, 2, 3, 4, 5]
    assert result.degraded is False
    assert result.degraded_reason is None


async def test_an_explicit_sort_reorders_the_matched_set_rather_than_widening_it(config):
    """§5.3. Picking a sort must not resurrect what relevance just ruled out."""
    scores = [0.91, 0.62, 0.44, 0.02, 0.001]
    relevance = build(FakeSearchRepository([1, 2, 3, 4, 5]), StubReranker(scores), config)
    # The repository applies the sort, so a price-ordered page arrives in a different order.
    sorted_repo = FakeSearchRepository([3, 1, 2, 5, 4])
    by_price = build(sorted_repo, StubReranker(scores), config)

    matched = await relevance.search(SearchQuery(q="olive oil"))
    priced = await by_price.search(SearchQuery(q="olive oil", explicit=_price_sort()))

    assert set(priced.product_ids) == set(matched.product_ids), "the same products qualify"
    assert priced.product_ids == [3, 1, 2], "in the order the database sorted them"
    assert priced.total == matched.total


async def test_an_explicit_sort_still_drops_the_irrelevant_tail(config):
    repository = FakeSearchRepository([5, 4, 3, 2, 1], total=5)
    service = build(repository, StubReranker([0.001, 0.02, 0.44, 0.62, 0.91]), config)

    result = await service.search(SearchQuery(q="olive oil", explicit=_price_sort()))

    assert result.product_ids == [3, 2, 1], "5 and 4 scored below the floor"
    assert result.total == 3


async def test_an_explicit_sort_is_not_reported_as_reranked(config):
    repository = FakeSearchRepository([1, 2, 3])
    service = build(repository, StubReranker([0.91, 0.62, 0.44]), config)

    result = await service.search(SearchQuery(q="olive oil", explicit=_price_sort()))

    assert result.reranked is False, "the reranker chose the members, not the order"
    assert result.effective_sort == "price_asc"


async def test_arabic_queries_are_judged_against_the_arabic_floor():
    config = settings(RERANK_MIN_SCORE=0.50, RERANK_MIN_SCORE_AR=0.10, RERANK_GAP_RATIO=0.0)
    repository = FakeSearchRepository([1, 2, 3])
    service = build(repository, StubReranker([0.40, 0.30, 0.05]), config)

    result = await service.search(SearchQuery(q="شيء حامض للفتوش"))

    assert result.product_ids == [1, 2], "0.40 and 0.30 clear the Arabic floor but not the English"


async def test_the_cutoff_can_be_switched_off_entirely():
    config = settings(RERANK_MIN_SCORE=0.0, RERANK_MIN_SCORE_AR=0.0, RERANK_GAP_RATIO=0.0)
    repository = FakeSearchRepository([1, 2, 3, 4, 5], total=5)
    service = build(repository, StubReranker([0.91, 0.62, 0.44, 0.02, 0.001]), config)

    result = await service.search(SearchQuery(q="sour ingredient for fattoush"))

    assert result.product_ids == [1, 2, 3, 4, 5]
    assert result.total == 5
