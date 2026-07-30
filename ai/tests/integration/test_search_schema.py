from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import container, open_scope
from app.core.vector_schema import EMBEDDING_VECTOR_DIMENSIONS

# The search schema this service owns. Nothing here exercises search behaviour, because there is
# none yet — these tests pin the structural guarantees the rest of the feature will assume.

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def _scalar(sql: str, **params):
    async with open_scope() as scope:
        return await scope.resolve(AsyncSession).scalar(text(sql), params)


async def _product_id(name: str) -> int:
    return await _scalar("SELECT id FROM products WHERE name = :name", name=name)


class TestExtensions:
    @pytest.mark.parametrize("extension", ["vector", "pg_trgm"])
    async def test_extension_is_installed(self, app, extension: str):
        installed = await _scalar(
            "SELECT count(*) FROM pg_extension WHERE extname = :name", name=extension
        )
        assert installed == 1, (
            f"the {extension!r} extension is missing — the test database is probably a stock "
            "postgres image rather than pgvector/pgvector:pg18"
        )


class TestSchema:
    @pytest.mark.parametrize(
        "table",
        [
            "ai_search_documents",
            "ai_search_index_jobs",
            "ai_search_events",
            "ai_search_query_embeddings",
        ],
    )
    async def test_table_exists(self, app, table: str):
        found = await _scalar(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :name",
            name=table,
        )
        assert found == 1

    @pytest.mark.parametrize(
        "index",
        [
            "ix_ai_search_documents_en",
            "ix_ai_search_documents_simple",
            "ix_ai_search_index_jobs_claim",
            "ix_ai_search_events_created_at",
            "ix_ai_search_events_zero_result",
            "ix_ai_search_query_embeddings_expires_at",
        ],
    )
    async def test_index_exists(self, app, index: str):
        found = await _scalar("SELECT count(*) FROM pg_indexes WHERE indexname = :name", name=index)
        assert found == 1


class TestVectorColumns:
    """§10.2's embedding storage. Structural, because the semantic leg assumes all of it."""

    @pytest.mark.parametrize("slot", ["embedding", "fallback_embedding"])
    async def test_the_vector_column_is_the_width_the_model_was_chosen_at(self, app, slot: str):
        # atttypmod carries vector(n)'s n. A column built at a different width than
        # EMBEDDING_DIMENSIONS would not fail until the first write, after a backfill had been
        # paid for — which is why the boot guard compares the two.
        width = await _scalar(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'ai_search_documents'::regclass AND attname = :name",
            name=slot,
        )
        assert width == EMBEDDING_VECTOR_DIMENSIONS

    @pytest.mark.parametrize("slot", ["embedding", "fallback_embedding"])
    async def test_the_vector_column_is_nullable(self, app, slot: str):
        # §10.2 forbids NOT NULL before the initial backfill completes. Every document is NULL
        # here the moment this migration lands, and the fallback column stays NULL for good when
        # no second provider is configured.
        nullable = await _scalar(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'ai_search_documents' AND column_name = :name",
            name=slot,
        )
        assert nullable == "YES"

    @pytest.mark.parametrize(
        "index",
        ["ix_ai_search_documents_embedding", "ix_ai_search_documents_fallback_embedding"],
    )
    async def test_the_vector_index_is_hnsw_with_cosine_operators(self, app, index: str):
        # Retrieval ranks by `1 - (embedding <=> :q)`. An index built for a different operator
        # class is never chosen, the query silently falls back to a sequential scan, and the only
        # symptom is latency at a catalog size this test does not have.
        definition = await _scalar(
            "SELECT indexdef FROM pg_indexes WHERE indexname = :name", name=index
        )
        assert "USING hnsw" in definition
        assert "vector_cosine_ops" in definition


class TestCatalogForeignKeys:
    @pytest.mark.parametrize("table", ["ai_search_documents", "ai_search_index_jobs"])
    async def test_foreign_key_to_products_exists_and_cascades(self, app, table: str):
        row = (
            await _scalar(
                "SELECT cast(confdeltype AS text) FROM pg_constraint "
                "WHERE conrelid = cast(:table AS regclass) AND contype = 'f'",
                table=table,
            )
            or ""
        )
        # 'c' is ON DELETE CASCADE. Without it a deleted product could strand a search document.
        assert row == "c", f"{table} has no cascading foreign key to products"

    async def test_a_document_cannot_reference_a_product_that_does_not_exist(self, app, catalog):
        # The whole point of keeping a real foreign key: the database refuses, rather than the
        # index quietly accumulating rows pointing at nothing.
        with pytest.raises(IntegrityError):
            async with open_scope() as scope:
                await scope.resolve(AsyncSession).execute(
                    text(
                        "INSERT INTO ai_search_documents "
                        "(product_id, document_text, document_hash, document_version) "
                        "VALUES (999999, 'orphan', 'h', 1)"
                    )
                )

    async def test_deleting_a_product_clears_its_search_rows(self, app, catalog):
        product_id = await _product_id("Beta Stove")
        async with open_scope() as scope:
            session = scope.resolve(AsyncSession)
            await session.execute(
                text("INSERT INTO ai_search_index_jobs (product_id) VALUES (:pid)"),
                {"pid": product_id},
            )
            await session.execute(
                text(
                    "INSERT INTO ai_search_documents "
                    "(product_id, document_text, document_hash, document_version) "
                    "VALUES (:pid, 'x', 'h', 1)"
                ),
                {"pid": product_id},
            )

        async with open_scope() as scope:
            await scope.resolve(AsyncSession).execute(
                text("DELETE FROM products WHERE id = :pid"), {"pid": product_id}
            )

        for table in ("ai_search_index_jobs", "ai_search_documents"):
            remaining = await _scalar(
                f"SELECT count(*) FROM {table} WHERE product_id = :pid", pid=product_id
            )
            assert remaining == 0, f"{table} kept a row for a deleted product"


class TestJobQueue:
    async def test_repeated_edits_coalesce_into_one_row(self, app, catalog):
        # product_id is the primary key precisely so a burst of edits leaves one unit of work
        # rather than a pile the worker would collapse later.
        product_id = await _product_id("Alpha Tent")
        async with open_scope() as scope:
            session = scope.resolve(AsyncSession)
            for _ in range(3):
                await session.execute(
                    text(
                        "INSERT INTO ai_search_index_jobs (product_id) VALUES (:pid) "
                        "ON CONFLICT (product_id) DO UPDATE SET requested_at = now(), "
                        "attempts = 0, next_attempt_at = now()"
                    ),
                    {"pid": product_id},
                )

        queued = await _scalar(
            "SELECT count(*) FROM ai_search_index_jobs WHERE product_id = :pid", pid=product_id
        )
        assert queued == 1

    async def test_a_claimed_job_is_invisible_to_a_second_worker(self, app, catalog):
        # SKIP LOCKED is what lets more than one worker run without double-embedding a product.
        product_id = await _product_id("Alpha Tent")
        async with open_scope() as scope:
            await scope.resolve(AsyncSession).execute(
                text("INSERT INTO ai_search_index_jobs (product_id) VALUES (:pid)"),
                {"pid": product_id},
            )

        claim = text(
            "SELECT product_id FROM ai_search_index_jobs "
            "WHERE next_attempt_at <= now() "
            "ORDER BY requested_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        assert container.session_factory is not None
        async with container.session_factory() as first, first.begin():
            claimed = (await first.execute(claim)).scalar_one_or_none()
            assert claimed == product_id

            # A second worker, while the first still holds its transaction open.
            async with container.session_factory() as second, second.begin():
                assert (await second.execute(claim)).scalar_one_or_none() is None


class TestScopes:
    async def test_each_scope_is_independent(self, app):
        # The read scope and the write scope around an embedding call must share no session and
        # no cached instance, so nothing survives across the provider call by accident.
        async with open_scope() as first:
            first_session = first.resolve(AsyncSession)
        async with open_scope() as second:
            second_session = second.resolve(AsyncSession)
        assert first_session is not second_session

    async def test_a_scope_holds_no_connection_after_it_closes(self, app):
        pool = container.engine.sync_engine.pool
        async with open_scope() as scope:
            await scope.resolve(AsyncSession).scalar(text("SELECT 1"))
            held = pool.checkedout()
        assert pool.checkedout() == held - 1
