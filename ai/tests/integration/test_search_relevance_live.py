from __future__ import annotations

import os

import pytest

from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.irelevance_service import IRelevanceService
from app.application.iservices.isearch_service import ISearchService
from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.services.index_service import IndexService
from app.application.services.search_service import SearchService
from app.core.config import Settings
from app.core.container import container
from app.core.registry import _build_embedding_providers

pytestmark = [
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"),
    pytest.mark.skipif(
        os.environ.get("RELEVANCE_LIVE") != "1",
        reason="live provider run; set RELEVANCE_LIVE=1 to include it",
    ),
]

LIVE_OVERALL_RECALL = 1.0
LIVE_ARABIC_RECALL = 1.0
LIVE_ARABIC_MRR = 1.0
LIVE_ENGLISH_RECALL = 1.0
LIVE_ENGLISH_MRR = 1.0
LIVE_NDCG = 1.0


async def _live_report(app, beit_catalog):
    settings = container.resolve(Settings)
    if not settings.EMBEDDING_PROVIDER or not settings.EMBEDDING_API_KEY:
        pytest.skip("EMBEDDING_PROVIDER and EMBEDDING_API_KEY must be set for a live run")

    previous_flag = settings.SMART_SEARCH_ENABLED
    settings.SMART_SEARCH_ENABLED = True
    container.bind_instance(EmbeddingProviders, _build_embedding_providers(settings))
    container.bind(IIndexService, IndexService, singleton=True)
    container.bind(ISearchService, SearchService, singleton=True)

    service = container.resolve(IIndexService)
    await service.sweep()
    await service.drain(max_batches=50)
    await service.refresh_coverage()
    report = await container.resolve(IRelevanceService).score(label="live")

    settings.SMART_SEARCH_ENABLED = previous_flag
    container.bind_instance(EmbeddingProviders, EmbeddingProviders(primary=None))
    container.bind(IIndexService, IndexService, singleton=True)
    container.bind(ISearchService, SearchService, singleton=True)
    return report


async def test_the_semantic_path_meets_every_gate_in_both_languages(app, beit_catalog):
    report = await _live_report(app, beit_catalog)

    arabic = next(s for s in report.by_language if s.language == "ar")
    assert arabic.recall_at_5 >= LIVE_ARABIC_RECALL, report.gate_failures
    assert arabic.mrr >= LIVE_ARABIC_MRR

    english = next(s for s in report.by_language if s.language == "en")
    assert english.recall_at_5 >= LIVE_ENGLISH_RECALL
    assert english.mrr >= LIVE_ENGLISH_MRR

    assert report.gates_pass, report.gate_failures
    assert report.overall.recall_at_5 >= LIVE_OVERALL_RECALL
    assert report.overall.ndcg_at_10 >= LIVE_NDCG

    nonsense = next(r for r in report.results if r.case_id == "en-nonsense")
    assert nonsense.passed and nonsense.total == 0

    for case_id in ("en-not-in-catalog", "ar-not-in-catalog"):
        case = next(r for r in report.results if r.case_id == case_id)
        assert case.passed, f"{case_id}: {case.detail}"
