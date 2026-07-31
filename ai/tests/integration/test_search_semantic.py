from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select, text, update

from app.application.dtos.search_dto import SearchQuery
from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.isearch_service import ISearchService
from app.application.llm.iembedding_client import (
    ERROR_RATE_LIMITED,
    ERROR_UNAUTHORIZED,
    EmbeddingError,
)
from app.application.search.query_cache import query_cache_key
from app.core.container import container, open_scope
from app.core.vector_schema import FALLBACK_SLOT
from app.infrastructure.irepositories.isearch_index_repository import ISearchIndexRepository
from app.infrastructure.models.search import SearchDocument, SearchQueryEmbedding
from tests.unit.fakes import FakeEmbeddingClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

documents = SearchDocument.__table__
cache = SearchQueryEmbedding.__table__


async def _scalar(stmt):
    async with container.session_factory() as session, session.begin():
        return await session.scalar(stmt)


async def _index(client=None):
    service = container.resolve(IIndexService)
    await service.sweep()
    await service.drain(max_batches=50)
    await service.refresh_coverage()
    return client


def _search(q: str, **kwargs):
    return container.resolve(ISearchService).search(SearchQuery(q=q, **kwargs))


class TestTheSemanticLegRuns:
    async def test_a_text_query_reports_hybrid_and_is_not_degraded(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()

        result = await _search("olive oil")

        assert result.mode == "hybrid"
        assert result.degraded is False
        assert result.degraded_reason is None

    async def test_the_ranker_version_records_that_a_leg_was_added(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()

        assert (await _search("olive oil")).ranker_version == "3"

    async def test_an_honest_empty_result_is_not_reported_as_a_broken_index(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()

        result = await _search("zzzznotathing")

        assert result.total == 0
        assert result.mode == "hybrid"
        assert result.degraded is False, "an empty semantic result was reported as a fault"

    async def test_a_constraint_fallback_still_reports_the_semantic_leg_ran(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()

        result = await _search("zzzznotathing under $30")

        assert result.degraded is False
        assert result.degraded_reason is None

    async def test_a_pure_constraint_query_never_calls_the_provider(
        self, app, beit_catalog, embedding, smart_search
    ):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index()

        result = await _search("under $30")

        assert result.mode == "filters_only"
        assert client.query_calls == []


class TestTheQueryCache:
    async def test_a_repeated_query_does_not_call_the_provider_again(
        self, app, beit_catalog, embedding, smart_search
    ):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index()

        await _search("olive oil for frying")
        await _search("olive oil for frying")

        assert len(client.query_calls) == 1

    async def test_the_cache_key_is_never_the_shopper_s_words(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()

        await _search("olive oil for frying")

        keys = await _scalar(select(func.string_agg(cache.c.cache_key, ",")))
        assert "olive" not in keys
        assert len(keys.split(",")[0]) == 64

    async def test_an_expired_row_is_not_served(self, app, beit_catalog, embedding, smart_search):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index()
        await _search("olive oil for frying")

        async with container.session_factory() as session, session.begin():
            await session.execute(
                update(cache).values(expires_at=text("now() - interval '1 hour'"))
            )
        await _search("olive oil for frying")

        assert len(client.query_calls) == 2

    async def test_the_prune_removes_expired_rows_and_leaves_live_ones(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()
        await _search("olive oil")
        await _search("cedar coasters")
        async with container.session_factory() as session, session.begin():
            await session.execute(
                update(cache)
                .where(cache.c.cache_key.in_(select(cache.c.cache_key).limit(1)))
                .values(expires_at=text("now() - interval '1 hour'"))
            )

        async with open_scope() as scope:
            pruned = await scope.resolve(ISearchIndexRepository).prune_query_cache()

        assert pruned == 1
        assert await _scalar(select(func.count()).select_from(cache)) == 1

    async def test_the_prune_runs_on_its_own_clock_rather_than_every_sweep(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        service = container.resolve(IIndexService)
        await service.sweep()

        assert await service.prune_query_cache() == 0

    async def test_a_different_model_gets_a_different_row(self, app):
        first = query_cache_key(
            semantic_text="olive oil", language="en", embedding_model="model-a", dimensions=768
        )
        second = query_cache_key(
            semantic_text="olive oil", language="en", embedding_model="model-b", dimensions=768
        )
        assert first != second


class TestDegradation:
    async def test_a_dead_provider_serves_lexical_results_rather_than_failing(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()
        embedding(
            primary=FakeEmbeddingClient(fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED))
        )

        result = await _search("olive oil")

        assert result.mode == "lexical"
        assert result.degraded is True
        assert result.degraded_reason == "embedding_unavailable"
        assert result.product_ids, "the lexical leg should still have answered"

    async def test_the_breaker_stops_every_query_paying_the_same_failure(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding()
        await _index()

        client = FakeEmbeddingClient(fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED))
        embedding(primary=client)
        threshold = smart_search.EMBEDDING_BREAKER_FAILURES
        for _ in range(threshold + 3):
            result = await _search("olive oil")
            assert result.degraded_reason == "embedding_unavailable"

        assert len(client.query_calls) == threshold, (
            "the circuit did not open; every query paid for the same dead provider"
        )

    async def test_indexing_and_searching_share_one_provider_s_circuit(
        self, app, beit_catalog, embedding, smart_search
    ):
        client = FakeEmbeddingClient(fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED))
        embedding(primary=client)
        await _index()

        calls_after_indexing = len(client.query_calls) + len(client.document_calls)
        await _search("olive oil")

        assert len(client.query_calls) + len(client.document_calls) == calls_after_indexing

    async def test_an_unembedded_column_reports_the_index_not_the_provider(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding(
            primary=FakeEmbeddingClient(fail_with=EmbeddingError("down", code=ERROR_RATE_LIMITED))
        )
        await _index()
        embedding()

        result = await _search("olive oil")

        assert result.mode == "lexical"
        assert result.degraded_reason == "index_incomplete"

    async def test_the_flag_being_off_is_reported_as_configuration_not_a_fault(
        self, app, beit_catalog, embedding
    ):
        embedding()
        await _index()

        result = await _search("olive oil")

        assert result.mode == "lexical"
        assert result.degraded_reason == "feature_disabled"

    async def test_a_failing_primary_falls_over_to_the_second_column(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding(
            primary=FakeEmbeddingClient(model="primary-model"),
            fallback=FakeEmbeddingClient(model="fallback-model"),
        )
        await _index()
        embedding(
            primary=FakeEmbeddingClient(
                model="primary-model", fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED)
            ),
            fallback=FakeEmbeddingClient(model="fallback-model"),
        )

        result = await _search("olive oil")

        assert result.mode == "hybrid", "failover did not produce a working semantic search"
        assert result.degraded is False

    async def test_a_query_vector_is_never_compared_against_the_other_model_s_column(
        self, app, beit_catalog, embedding, smart_search
    ):
        embedding(
            primary=FakeEmbeddingClient(model="primary-model"),
            fallback=FakeEmbeddingClient(model="fallback-model"),
        )
        await _index()
        async with container.session_factory() as session, session.begin():
            await session.execute(update(documents).values(fallback_embedding=None))
        await container.resolve(IIndexService).refresh_coverage()

        embedding(
            primary=FakeEmbeddingClient(
                model="primary-model", fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED)
            ),
            fallback=FakeEmbeddingClient(model="fallback-model"),
        )
        result = await _search("olive oil")

        assert result.mode == "lexical"
        assert result.degraded_reason == "index_incomplete"
        assert not container.resolve(
            __import__("app.core.index_state", fromlist=["IndexCoverage"]).IndexCoverage
        ).semantic(FALLBACK_SLOT)


class TestTransactionDiscipline:
    async def test_no_connection_is_held_while_the_provider_is_called(
        self, app, beit_catalog, embedding, smart_search
    ):
        pool = container.engine.sync_engine.pool
        observed: list[int] = []

        class Observing(FakeEmbeddingClient):
            async def embed_query(self, text_: str):
                observed.append(pool.checkedout())
                return await super().embed_query(text_)

        embedding(primary=Observing())
        await _index()
        await _search("olive oil for frying")

        assert observed, "the provider was never called; the assertion proved nothing"
        assert observed == [0], (
            f"a database connection was held across the provider call: {observed}"
        )
