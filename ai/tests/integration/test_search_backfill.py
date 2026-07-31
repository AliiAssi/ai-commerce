from __future__ import annotations

import math
import os

import pytest
from sqlalchemy import func, select, update

from app.application.iservices.iindex_service import IIndexService
from app.application.llm.iembedding_client import (
    ERROR_RATE_LIMITED,
    ERROR_UNAUTHORIZED,
    EmbeddingError,
)
from app.core.config import Settings
from app.core.container import container
from app.core.index_state import IndexCoverage
from app.core.vector_schema import FALLBACK_SLOT, PRIMARY_SLOT
from app.infrastructure.database.store_tables import products
from app.infrastructure.models.search import SearchDocument, SearchIndexJob
from tests.unit.fakes import FakeEmbeddingClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

documents = SearchDocument.__table__
jobs = SearchIndexJob.__table__


async def _scalar(stmt):
    async with container.session_factory() as session, session.begin():
        return await session.scalar(stmt)


async def _index_everything(service: IIndexService) -> None:
    await service.sweep()
    await service.drain(max_batches=50)
    await service.refresh_coverage()


def _service() -> IIndexService:
    return container.resolve(IIndexService)


class TestBackfill:
    async def test_a_full_sweep_embeds_every_active_product(self, app, beit_catalog, embedding):
        embedding()
        await _index_everything(_service())

        embedded = await _scalar(
            select(func.count()).select_from(documents).where(documents.c.embedding.is_not(None))
        )
        assert embedded == len(beit_catalog)

    async def test_the_model_and_width_are_stored_beside_every_vector(
        self, app, beit_catalog, embedding
    ):
        embedding(primary=FakeEmbeddingClient(model="a-named-model"))
        await _index_everything(_service())

        rows = await _scalar(
            select(func.count())
            .select_from(documents)
            .where(
                documents.c.embedding_model == "a-named-model",
                documents.c.embedding_dimensions == 768,
            )
        )
        assert rows == len(beit_catalog)

    async def test_each_claimed_batch_costs_one_provider_call(self, app, beit_catalog, embedding):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index_everything(_service())

        batch_size = container.resolve(Settings).SEARCH_INDEX_BATCH_SIZE
        assert len(client.document_calls) == math.ceil(len(beit_catalog) / batch_size)
        assert sum(len(call) for call in client.document_calls) == len(beit_catalog)
        assert max(len(call) for call in client.document_calls) <= batch_size

    async def test_a_second_sweep_embeds_nothing(self, app, beit_catalog, embedding):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index_everything(_service())

        calls_after_backfill = len(client.document_calls)
        await _index_everything(_service())

        assert len(client.document_calls) == calls_after_backfill
        assert await _scalar(select(func.count()).select_from(jobs)) == 0

    async def test_both_columns_are_filled_when_two_providers_are_configured(
        self, app, beit_catalog, embedding
    ):
        embedding(
            primary=FakeEmbeddingClient(model="primary-model"),
            fallback=FakeEmbeddingClient(model="fallback-model"),
        )
        await _index_everything(_service())

        for column, model in (
            (documents.c.embedding_model, "primary-model"),
            (documents.c.fallback_embedding_model, "fallback-model"),
        ):
            filled = await _scalar(
                select(func.count()).select_from(documents).where(column == model)
            )
            assert filled == len(beit_catalog), f"{model} did not fill its column"

    async def test_an_unconfigured_fallback_column_stays_empty_and_quiet(
        self, app, beit_catalog, embedding
    ):
        embedding()
        await _index_everything(_service())
        await _service().sweep()

        assert await _scalar(select(func.count()).select_from(jobs)) == 0
        assert (
            await _scalar(
                select(func.count())
                .select_from(documents)
                .where(documents.c.fallback_embedding.is_not(None))
            )
            == 0
        )


class TestVectorDrift:
    async def test_a_missing_vector_is_drift_even_though_the_text_is_current(
        self, app, beit_catalog, embedding
    ):
        embedding()
        await _index_everything(_service())
        async with container.session_factory() as session, session.begin():
            await session.execute(update(documents).values(embedding=None))

        enqueued = (await _service().sweep()).enqueued

        assert enqueued == len(beit_catalog)

    async def test_changing_the_model_re_embeds_the_catalog(self, app, beit_catalog, embedding):
        embedding(primary=FakeEmbeddingClient(model="old-model"))
        await _index_everything(_service())

        embedding(primary=FakeEmbeddingClient(model="new-model"))
        await _index_everything(_service())

        stale = await _scalar(
            select(func.count())
            .select_from(documents)
            .where(documents.c.embedding_model != "new-model")
        )
        assert stale == 0

    async def test_editing_the_text_re_embeds_only_that_product(self, app, beit_catalog, embedding):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index_everything(_service())

        async with container.session_factory() as session, session.begin():
            await session.execute(
                update(products)
                .where(products.c.name == "Baladi Extra Virgin Olive Oil")
                .values(description="A different description entirely.")
            )
        calls_after_backfill = len(client.document_calls)
        await _index_everything(_service())

        assert len(client.document_calls) == calls_after_backfill + 1
        assert client.document_calls[-1] == [
            "Name: Baladi Extra Virgin Olive Oil\n"
            "Category: Olive Oil & Za'atar\n"
            "Origin: Koura, North Lebanon\n"
            "Description: A different description entirely."
        ], "an edit re-embedded more than the row that changed"

    async def test_configuring_a_fallback_later_does_not_re_embed_the_primary(
        self, app, beit_catalog, embedding
    ):
        primary = FakeEmbeddingClient(model="primary-model")
        embedding(primary=primary)
        await _index_everything(_service())
        calls_after_backfill = len(primary.document_calls)

        embedding(primary=primary, fallback=FakeEmbeddingClient(model="fallback-model"))
        await _index_everything(_service())

        assert len(primary.document_calls) == calls_after_backfill, (
            "the primary column was re-embedded because a different slot was stale"
        )


class TestProviderFailure:
    async def test_a_new_product_is_still_stored_lexically_when_embedding_fails(
        self, app, beit_catalog, embedding
    ):
        embedding(
            primary=FakeEmbeddingClient(fail_with=EmbeddingError("down", code=ERROR_RATE_LIMITED))
        )
        await _index_everything(_service())

        stored = await _scalar(select(func.count()).select_from(documents))
        assert stored == len(beit_catalog)
        assert (
            await _scalar(
                select(func.count())
                .select_from(documents)
                .where(documents.c.embedding.is_not(None))
            )
            == 0
        )

    async def test_an_existing_document_is_left_alone_when_embedding_fails(
        self, app, beit_catalog, embedding
    ):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index_everything(_service())

        async with container.session_factory() as session, session.begin():
            await session.execute(
                update(products)
                .where(products.c.name == "Baladi Extra Virgin Olive Oil")
                .values(description="Edited while the provider is down.")
            )
        client.set_failure(EmbeddingError("down", code=ERROR_RATE_LIMITED))
        await _service().sweep()
        await _service().drain(max_batches=5)

        stored_text = await _scalar(
            select(documents.c.document_text)
            .select_from(documents.join(products, products.c.id == documents.c.product_id))
            .where(products.c.name == "Baladi Extra Virgin Olive Oil")
        )
        assert "Edited while the provider is down." not in stored_text
        assert await _scalar(select(func.count()).select_from(jobs)) >= 1

    async def test_a_provider_failure_records_a_code_never_a_message(
        self, app, beit_catalog, embedding
    ):
        embedding(
            primary=FakeEmbeddingClient(
                fail_with=EmbeddingError("secret-key-value leaked", code=ERROR_RATE_LIMITED)
            )
        )
        await _index_everything(_service())

        code = await _scalar(select(jobs.c.last_error_code).limit(1))
        assert code == "embedding_rate_limited"
        assert "secret" not in code

    async def test_a_revoked_key_stops_immediately_instead_of_retrying_to_the_cap(
        self, app, beit_catalog, embedding
    ):
        embedding(
            primary=FakeEmbeddingClient(fail_with=EmbeddingError("nope", code=ERROR_UNAUTHORIZED))
        )
        await _index_everything(_service())

        failed = await _service().failed_jobs()
        assert len(failed) == len(beit_catalog)
        assert all(job.last_error_code == "embedding_unauthorized" for job in failed)

    async def test_a_rate_limit_backs_off_rather_than_exhausting_the_job(
        self, app, beit_catalog, embedding
    ):
        embedding(
            primary=FakeEmbeddingClient(
                fail_with=EmbeddingError("slow down", code=ERROR_RATE_LIMITED)
            )
        )
        await _index_everything(_service())

        assert await _service().failed_jobs() == []
        assert await _service().pending_count() == len(beit_catalog)

    async def test_a_failing_provider_never_destroys_a_stored_vector(
        self, app, beit_catalog, embedding
    ):
        client = FakeEmbeddingClient()
        embedding(primary=client)
        await _index_everything(_service())

        client.set_failure(EmbeddingError("down", code=ERROR_RATE_LIMITED))
        await _service().enqueue_all_active(reset=True)
        await _service().drain(max_batches=5)

        surviving = await _scalar(
            select(func.count()).select_from(documents).where(documents.c.embedding.is_not(None))
        )
        assert surviving == len(beit_catalog)


class TestSemanticCoverage:
    async def test_vector_coverage_is_separate_from_document_coverage(
        self, app, beit_catalog, embedding
    ):
        embedding(
            primary=FakeEmbeddingClient(fail_with=EmbeddingError("down", code=ERROR_RATE_LIMITED))
        )
        await _index_everything(_service())

        coverage = container.resolve(IndexCoverage)
        assert coverage.ready, "documents were written; the lexical leg should still be on step 3"
        assert not coverage.semantic(PRIMARY_SLOT), "no vectors were stored, yet the slot is ready"

    async def test_a_fully_embedded_catalog_opens_the_semantic_slot(
        self, app, beit_catalog, embedding
    ):
        embedding()
        await _index_everything(_service())

        coverage = container.resolve(IndexCoverage)
        assert coverage.semantic(PRIMARY_SLOT)
        assert not coverage.semantic(FALLBACK_SLOT), "an unconfigured slot reported itself ready"

    async def test_an_unreported_slot_is_never_ready(self, app):
        assert not IndexCoverage().semantic(PRIMARY_SLOT)
