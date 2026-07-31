from __future__ import annotations

import os

import pytest

from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.irelevance_service import IRelevanceService
from app.core.container import container
from app.core.registry import configure_relevance
from app.core.relevance import RelevanceCorpus

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

BASELINE_OVERALL_RECALL = 0.62
BASELINE_ARABIC_RECALL = 0.34
BASELINE_ENGLISH_RECALL = 0.96
BASELINE_ENGLISH_MRR = 0.94

NEEDS_A_MODEL = {"en-natural-sweetener", "en-glass-not-glaze"}


@pytest.fixture
async def report(app, beit_catalog):
    configure_relevance(container)
    await container.resolve(IIndexService).sweep()
    await container.resolve(IIndexService).drain(max_batches=50)
    await container.resolve(IIndexService).refresh_coverage()
    return await container.resolve(IRelevanceService).score(label="test")


class TestCorpusIntegrity:
    async def test_every_product_the_corpus_names_exists_in_the_catalog(self, report):
        unknown = [r for r in [*report.results, *report.drafts] if "unknown_product" in r.failures]

        assert unknown == [], [f"{r.case_id}: {r.detail}" for r in unknown]

    async def test_the_corpus_is_scored_against_the_document_leg(self, report):
        assert report.retrieval_path.startswith("documents")
        assert report.index_coverage == "46/46"

    async def test_every_case_is_judged_and_gates(self, report):
        corpus = container.resolve(RelevanceCorpus)
        drafts = [case.id for case in corpus.cases if not case.is_gate]

        assert drafts == [], (
            "a draft case is back in the corpus. Every case was reviewed and either promoted or "
            "deleted on 2026-07-31; a new one has to be judged before it is added, not after."
        )
        assert report.draft_cases == 0
        assert all(r.source == "spec" for r in report.results)
        assert report.scored_cases == len(corpus.cases)


class TestDeterministicGates:
    async def test_exact_product_names_rank_first_every_time(self, report):
        assert report.overall.exact_name_rate == 1.0

    async def test_deterministic_filter_precision_is_total(self, report):
        assert report.overall.filter_precision == 1.0
        for score in report.by_language:
            assert score.filter_precision == 1.0, f"{score.language} filters"


class TestEnglishAlreadyPasses:
    async def test_english_recall_and_mrr_are_perfect(self, report):
        english = next(s for s in report.by_language if s.language == "en")

        assert english.recall_at_5 >= BASELINE_ENGLISH_RECALL
        assert english.mrr >= BASELINE_ENGLISH_MRR

    async def test_only_the_two_model_dependent_english_cases_fail(self, report):
        failing = {r.case_id for r in report.results if r.language == "en" and not r.passed}

        assert failing == NEEDS_A_MODEL, (
            "This module measures the degraded path, where no embedding provider and no reranker "
            "are configured. en-natural-sweetener needs the reranker to order the constraint "
            "fallback and en-glass-not-glaze needs it to outrank a pitcher with tumblers; every "
            "other English case is answered by deterministic retrieval alone."
        )


class TestArabicWithoutAModel:
    async def test_arabic_is_recorded_at_its_measured_floor(self, report):
        arabic = next(s for s in report.by_language if s.language == "ar")

        assert arabic.recall_at_5 >= BASELINE_ARABIC_RECALL

    async def test_the_degraded_path_still_falls_short_for_arabic(self, report):
        arabic = next(s for s in report.by_language if s.language == "ar")

        assert arabic.recall_at_5 < 0.90, (
            "Arabic recall meets §15's gate with no embedding provider configured. Either the "
            "suite grew a provider it should not have, or the catalog gained Arabic text — "
            "either way this module is no longer measuring the degraded path it claims to."
        )

    async def test_nothing_outside_arabic_and_the_two_known_cases_fails(self, report):
        unexpected = {
            r.case_id
            for r in report.results
            if r.language != "ar" and not r.passed and r.case_id not in NEEDS_A_MODEL
        }

        assert unexpected == set()


class TestRegressionFloor:
    async def test_overall_recall_has_not_regressed(self, report):
        assert report.overall.recall_at_5 >= BASELINE_OVERALL_RECALL

    async def test_the_relevance_floor_still_returns_nothing_for_nonsense(self, report):
        nonsense = next(r for r in report.results if r.case_id == "en-nonsense")

        assert nonsense.passed
        assert nonsense.total == 0
