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

# The semantic numbers, measured against the real provider.
#
# Skipped by default and on purpose. It costs provider calls, needs a key CI does not have, and
# the free tier that serves it started refusing part-way through ninety sequential calls during
# the phase-5 bake-off. Run it deliberately:
#
#   RELEVANCE_LIVE=1 EMBEDDING_PROVIDER=gemini EMBEDDING_MODEL=gemini-embedding-001 \
#     EMBEDDING_DIMENSIONS=768 EMBEDDING_API_KEY=... \
#     TEST_DATABASE_URL=... uv run pytest tests/integration/test_search_relevance_live.py
#
# It exists because nothing else can catch a regression in the semantic path. The rest of the
# suite runs with no provider, and the fake has no cross-lingual behaviour to regress.

pytestmark = [
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"),
    pytest.mark.skipif(
        os.environ.get("RELEVANCE_LIVE") != "1",
        reason="live provider run; set RELEVANCE_LIVE=1 to include it",
    ),
]

# Measured 2026-07-29 against gemini-embedding-001 @ 768 over the seeded 46-product catalog,
# 24 gating cases, SEARCH_SEMANTIC_MIN_SIMILARITY=0.645.
#
# Floors, not targets. The phase-5 lexical baseline they replace was overall R@5 0.75 with
# Arabic at 0.33 — the whole reason this phase exists is the second number.
LIVE_OVERALL_RECALL = 1.0
LIVE_ARABIC_RECALL = 1.0
LIVE_ARABIC_MRR = 1.0
LIVE_ENGLISH_RECALL = 1.0
LIVE_ENGLISH_MRR = 1.0
LIVE_NDCG = 1.0


async def _live_report(app, beit_catalog):
    """Bind the real provider, backfill, and score the corpus once."""
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
    """One live run, every assertion — deliberately not one test per gate.

    The autouse `_clean` truncates between tests, including the query-embedding cache, so a
    fixture shared by seven tests would re-embed all 105 corpus queries seven times: 735
    sequential calls against a free tier that starts timing out after roughly ninety. That is not
    a hypothetical — it is how this file failed the first time it was run, with `provider
    _unavailable` on the query leg and the whole report silently scored on the lexical fallback.
    Granularity is worth less than a measurement that is actually of the thing it names.
    """
    report = await _live_report(app, beit_catalog)

    # The number this phase exists for. §15 requires recall@5 >= 0.90 independently per language,
    # and Arabic — 0.33 on the lexical baseline, with four cases returning nothing at all — was
    # the only language that ever missed it.
    arabic = next(s for s in report.by_language if s.language == "ar")
    assert arabic.recall_at_5 >= LIVE_ARABIC_RECALL, report.gate_failures
    assert arabic.mrr >= LIVE_ARABIC_MRR

    # §15: an Arabic gain must not be bought with an English regression. English passed every
    # gate with no model at all, so the semantic leg's job in English is to change nothing.
    english = next(s for s in report.by_language if s.language == "en")
    assert english.recall_at_5 >= LIVE_ENGLISH_RECALL
    assert english.mrr >= LIVE_ENGLISH_MRR

    assert report.gates_pass, report.gate_failures
    assert report.overall.recall_at_5 >= LIVE_OVERALL_RECALL
    assert report.overall.ndcg_at_10 >= LIVE_NDCG

    # §7.4's empty-set rule, which is what the calibrated similarity floor buys. A rank-based
    # floor cannot express it: the nearest neighbour of nonsense still arrives at rank 1.
    nonsense = next(r for r in report.results if r.case_id == "en-nonsense")
    assert nonsense.passed and nonsense.total == 0

    # The harder half of the same rule. There is no espresso machine in the catalog, and
    # answering with the copper coffee set is a confident wrong page rather than an empty one.
    for case_id in ("en-not-in-catalog", "ar-not-in-catalog"):
        case = next(r for r in report.results if r.case_id == case_id)
        assert case.passed, f"{case_id}: {case.detail}"
