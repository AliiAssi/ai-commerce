from __future__ import annotations

import os

import pytest

from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.isearch_service import ISearchService
from app.application.rerank.ireranker import IReranker
from app.application.services.search_service import SearchService
from app.core.config import Settings
from app.core.container import container
from tests.integration.conftest import seed_beit_catalog, truncate_all
from tests.support.irelevance_service import IRelevanceService
from tests.support.lexical_reranker import LexicalReranker
from tests.support.relevance_service import GATE_PRECISION_AT_3, GATE_PRECISION_AT_5
from tests.support.wiring import configure_relevance

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

CAPPED_CASES = ("en-fattoush-in-stock", "en-tripoli-soap")


@pytest.fixture(scope="module")
async def report(app, seed_data):
    """The corpus scored once with the relevance cutoff live.

    tests/integration/test_search_relevance.py measures the degraded path, where no reranker is
    configured at all and every retrieved candidate is returned. This module is its opposite: a
    deterministic scorer stands in for the cross-encoder so the floor and the gap rule actually
    fire, and the corpus can assert what comes back rather than only how it is ordered.

    Module-scoped on purpose. Scoring the corpus is ~100 searches; per-test it would be ~1200,
    which is tolerable against a local socket and not against a remote TEST_DATABASE_URL.
    """
    settings = container.resolve(Settings)
    previous_reranker = container.resolve(IReranker)
    previously_enabled = settings.SMART_SEARCH_ENABLED

    settings.SMART_SEARCH_ENABLED = True
    container.bind_instance(IReranker, LexicalReranker())
    container.bind(ISearchService, SearchService, singleton=True)

    await truncate_all()
    await seed_beit_catalog(seed_data)
    configure_relevance(container)
    await container.resolve(IIndexService).sweep()
    await container.resolve(IIndexService).drain(max_batches=50)
    await container.resolve(IIndexService).refresh_coverage()
    try:
        yield await container.resolve(IRelevanceService).score(label="cutoff", enforce_cutoff=True)
    finally:
        settings.SMART_SEARCH_ENABLED = previously_enabled
        container.bind_instance(IReranker, previous_reranker)
        container.bind(ISearchService, SearchService, singleton=True)


class TestTheReportedRegression:
    async def test_the_fattoush_query_no_longer_drags_a_tail_of_homeware(self, report):
        case = next(r for r in report.results if r.case_id == "en-fattoush-in-stock")

        assert case.passed, case.detail

    async def test_it_returns_a_handful_rather_than_the_whole_candidate_set(self, report):
        case = next(r for r in report.results if r.case_id == "en-fattoush-in-stock")

        assert case.returned_count <= 4, case.returned

    async def test_the_soap_query_drops_the_one_tripoli_product_that_is_not_soap(self, report):
        case = next(r for r in report.results if r.case_id == "en-tripoli-soap")

        assert case.passed, case.detail
        assert case.returned_count == 2, case.returned


class TestPrecisionGates:
    async def test_precision_at_3_clears_its_gate(self, report):
        assert report.overall.precision_at_3 >= GATE_PRECISION_AT_3

    async def test_precision_at_5_clears_its_gate(self, report):
        assert report.overall.precision_at_5 >= GATE_PRECISION_AT_5

    async def test_every_capped_case_is_actually_measured(self, report):
        measured = {r.case_id for r in report.results if r.precision_at_3 is not None}

        assert "en-tripoli-soap" in measured, (
            "precision is only computed for cases marked exhaustive; if none are, the gates "
            "above are averaging an empty list and pass vacuously"
        )


class TestNothingElseRegressed:
    async def test_no_case_fails_on_the_count_that_did_not_fail_before(self, report):
        over_capped = {
            r.case_id
            for r in report.results
            if "too_many_results" in r.failures and r.case_id not in CAPPED_CASES
        }

        assert over_capped == set()

    async def test_the_cutoff_did_not_empty_out_queries_that_have_answers(self, report):
        """English only, and that is not a dodge.

        No embedding provider is configured here, so an Arabic query retrieves nothing from an
        English catalog and comes back empty before any reranking happens — the same degraded
        baseline test_search_relevance.py records at recall@5 0.34. Counting those would blame
        the floor for candidates it was never shown. The companion assertion below is what
        keeps that exemption honest: on Arabic the cutoff must not be what empties the results.
        """
        emptied = [
            r.case_id
            for r in report.results
            if r.language == "en" and r.returned_count == 0 and "missing_required" in r.failures
        ]

        assert emptied == [], (
            "the floor is filtering out products the corpus requires. Lower RERANK_MIN_SCORE "
            "rather than deleting the case."
        )

    async def test_nonsense_still_comes_back_empty(self, report):
        nonsense = next(r for r in report.results if r.case_id == "en-nonsense")

        assert nonsense.passed
        assert nonsense.returned_count == 0

    async def test_exact_names_still_rank_first(self, report):
        assert report.overall.exact_name_rate == 1.0

    async def test_filters_are_untouched_by_the_cutoff(self, report):
        assert report.overall.filter_precision == 1.0


class TestArabicIsNotJudgedHere:
    async def test_the_stand_in_scorer_declines_to_rank_arabic(self, report):
        arabic = [r for r in report.results if r.language == "ar"]

        assert arabic, "the corpus lost its Arabic cases"
        assert all(r.precision_at_3 is None for r in arabic), (
            "RERANK_MIN_SCORE_AR still has to be calibrated against a real multilingual "
            "reranker. LexicalReranker returns a neutral score for Arabic so this module "
            "neither passes nor fails Arabic precision — it abstains."
        )
