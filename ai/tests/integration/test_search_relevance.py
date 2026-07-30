from __future__ import annotations

import os

import pytest

from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.irelevance_service import IRelevanceService
from app.core.container import container
from app.core.relevance import RelevanceCorpus

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

# **What this module measures, and what it deliberately does not.**
#
# No embedding provider is configured for the suite (see the integration conftest), so every case
# here runs on §12's degraded path: lexical over the documents, fused with trigram. That is not a
# gap — it is the configuration the storefront falls back to whenever the provider is down, and it
# is the one this suite can measure identically on a developer machine and in CI, with no API key
# and no spend.
#
# The semantic numbers are therefore *not* pinned here. They cannot be: FakeEmbeddingClient hashes
# tokens into buckets and has no cross-lingual behaviour, so asserting Arabic recall against it
# would prove the fake rather than the model. They are pinned in `test_search_relevance_live.py`,
# which runs against the real provider and is skipped unless it is asked for, and recorded in
# SMART_SEARCH_PLAN.md.
#
# The phase-4 baseline, measured on 2026-07-29 against §12's step 3 over the seeded catalog and
# unchanged by phase 6 — which is the point of repeating it. These are floors, not targets: a
# change that quietly costs relevance fails here rather than being discovered later, where it
# would be indistinguishable from a model underperforming. Raise them when a phase genuinely
# improves the number; never lower one to make a run go green without saying so in
# SMART_SEARCH_PLAN.md.
BASELINE_OVERALL_RECALL = 0.75
BASELINE_ARABIC_RECALL = 0.33
BASELINE_ENGLISH_RECALL = 1.0
BASELINE_ENGLISH_MRR = 1.0


@pytest.fixture
async def report(app, beit_catalog):
    """Index the catalog, settle the coverage gate, and score the corpus once."""
    await container.resolve(IIndexService).sweep()
    await container.resolve(IIndexService).drain(max_batches=50)
    await container.resolve(IIndexService).refresh_coverage()
    return await container.resolve(IRelevanceService).score(label="test")


class TestCorpusIntegrity:
    async def test_every_product_the_corpus_names_exists_in_the_catalog(self, report):
        # A case naming a product the catalog does not have would score as a permanent relevance
        # miss and look exactly like a regression. It is a corpus bug and must read as one.
        unknown = [r for r in [*report.results, *report.drafts] if "unknown_product" in r.failures]

        assert unknown == [], [f"{r.case_id}: {r.detail}" for r in unknown]

    async def test_the_corpus_is_scored_against_the_document_leg(self, report):
        # The coverage gate is process state. A run that had not settled it would silently
        # measure §12's step 4 and report a number for the wrong retrieval path — which is
        # exactly what happened the first time this was run by hand.
        assert report.retrieval_path.startswith("documents")
        assert report.index_coverage == "46/46"

    async def test_drafts_are_scored_but_never_gate(self, report):
        corpus = container.resolve(RelevanceCorpus)
        drafts = [case for case in corpus.cases if not case.is_gate]

        assert drafts, "the corpus has no draft cases, so §15's 50+50 expansion has no runway"
        assert report.draft_cases == len(drafts)
        # A draft that failed must not appear among the gating results, or it would fail a
        # release on an expectation nobody has reviewed.
        assert all(r.source == "spec" for r in report.results)


class TestDeterministicGates:
    """The §15 gates that do not depend on a model and therefore must hold today."""

    async def test_exact_product_names_rank_first_every_time(self, report):
        assert report.overall.exact_name_rate == 1.0

    async def test_deterministic_filter_precision_is_total(self, report):
        # §15 requires 100%. Filters are parsed, not ranked — anything less is a parser bug, and
        # no embedding model will fix it.
        assert report.overall.filter_precision == 1.0
        for score in report.by_language:
            assert score.filter_precision == 1.0, f"{score.language} filters"


class TestEnglishAlreadyPasses:
    """English meets §15 with no model at all. That is the bar embeddings have to hold, not beat."""

    async def test_english_recall_and_mrr_are_perfect(self, report):
        english = next(s for s in report.by_language if s.language == "en")

        assert english.recall_at_5 >= BASELINE_ENGLISH_RECALL
        assert english.mrr >= BASELINE_ENGLISH_MRR

    async def test_every_english_case_passes(self, report):
        failing = [r.case_id for r in report.results if r.language == "en" and not r.passed]

        assert failing == []


class TestArabicWithoutAModel:
    """§2.1's gap, still exactly where it was — because this is the path with no model in it.

    Phase 6 moved Arabic recall from 0.33 to 1.00, and none of that shows here. It cannot: an
    Arabic query has no lexical route into an English catalog, so with the embedding provider
    absent the only Arabic cases that pass are the ones deterministic filters answer. Keeping the
    number pinned at 0.33 is what makes the degraded path's cost visible instead of assumed —
    this is what a shopper typing Arabic gets while the provider is down, and it is not good.
    """

    async def test_arabic_is_recorded_at_its_measured_floor(self, report):
        arabic = next(s for s in report.by_language if s.language == "ar")

        # Deliberately an inequality against a low number, not an assertion that Arabic works.
        assert arabic.recall_at_5 >= BASELINE_ARABIC_RECALL

    async def test_the_degraded_path_still_falls_short_for_arabic(self, report):
        # The replacement for phase 5's `test_arabic_does_not_yet_meet_the_release_gate`, which
        # was written to fail the moment Arabic was fixed. It has been fixed — with a provider —
        # and that test was removed in phase 6 rather than left asserting something now false
        # about the system. What remains true, and is worth pinning, is narrower: *without* a
        # provider Arabic still misses §15's gate, so nothing may quietly start treating the
        # lexical fallback as an acceptable Arabic experience.
        arabic = next(s for s in report.by_language if s.language == "ar")

        assert arabic.recall_at_5 < 0.90, (
            "Arabic recall meets §15's gate with no embedding provider configured. Either the "
            "suite grew a provider it should not have, or the catalog gained Arabic text — "
            "either way this module is no longer measuring the degraded path it claims to."
        )

    async def test_the_overall_gates_fail_only_because_of_arabic(self, report):
        # If an English case ever starts failing, the gate messages must not let it hide behind
        # the known Arabic shortfall.
        non_arabic_failures = [
            r.case_id for r in report.results if r.language != "ar" and not r.passed
        ]

        assert non_arabic_failures == []


class TestRegressionFloor:
    async def test_overall_recall_has_not_regressed(self, report):
        assert report.overall.recall_at_5 >= BASELINE_OVERALL_RECALL

    async def test_the_relevance_floor_still_returns_nothing_for_nonsense(self, report):
        # §7.4's empty-set rule, as scored rather than as asserted in isolation.
        nonsense = next(r for r in report.results if r.case_id == "en-nonsense")

        assert nonsense.passed
        assert nonsense.total == 0
