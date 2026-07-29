from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import ScopeFactory, container
from app.infrastructure.irepositories.iproduct_repository import IProductRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def _scalar(sql: str, **params):
    async with container.open_scope() as scope:
        return await scope.resolve(AsyncSession).scalar(text(sql), params)


class TestExtensions:
    @pytest.mark.parametrize("extension", ["vector", "pg_trgm"])
    async def test_extension_is_installed(self, client, extension: str):
        installed = await _scalar(
            "SELECT count(*) FROM pg_extension WHERE extname = :name", name=extension
        )
        assert installed == 1, (
            f"the {extension!r} extension is missing — the test database is probably a stock "
            "postgres image rather than pgvector/pgvector:pg18"
        )

    async def test_trigram_similarity_is_callable(self, client):
        similarity = await _scalar("SELECT similarity('zaatar', 'za''atar')")
        assert similarity > 0.4


class TestCatalogIndexes:
    @pytest.mark.parametrize("index", ["ix_products_name_trgm", "ix_products_origin_trgm"])
    async def test_trigram_index_exists(self, client, index: str):
        found = await _scalar("SELECT count(*) FROM pg_indexes WHERE indexname = :name", name=index)
        assert found == 1

    async def test_existing_fulltext_index_survives(self, client):
        # products.search_vector and its GIN index remain the fallback used whenever the AI
        # service is unreachable, so nothing may quietly remove them.
        found = await _scalar(
            "SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_products_search_vector'"
        )
        assert found == 1


class TestShortScopes:
    async def test_work_is_committed_when_the_scope_closes(self, client, _clean):
        async with container.open_scope() as scope:
            await scope.resolve(IProductRepository).create_category("Scoped", "scoped")

        found = await _scalar("SELECT count(*) FROM categories WHERE slug = 'scoped'")
        assert found == 1

    async def test_work_is_rolled_back_when_the_scope_raises(self, client, _clean):
        with pytest.raises(RuntimeError, match="boom"):
            async with container.open_scope() as scope:
                await scope.resolve(IProductRepository).create_category("Doomed", "doomed")
                raise RuntimeError("boom")

        found = await _scalar("SELECT count(*) FROM categories WHERE slug = 'doomed'")
        assert found == 0

    async def test_each_scope_is_independent(self, client, _clean):
        # The property the search proxy rests on: the scope before an outbound call and the one
        # after it share no session, no transaction, and no cached instance.
        async with container.open_scope() as first:
            first_session = first.resolve(AsyncSession)
            first_repo = first.resolve(IProductRepository)
        async with container.open_scope() as second:
            second_session = second.resolve(AsyncSession)
            second_repo = second.resolve(IProductRepository)

        assert first_session is not second_session
        assert first_repo is not second_repo

    async def test_a_scope_holds_no_connection_after_it_closes(self, client, _clean):
        # A slow call to the AI service must not sit on a pooled connection.
        pool = container.engine.sync_engine.pool
        async with container.open_scope() as scope:
            await scope.resolve(IProductRepository).list_categories()
            held = pool.checkedout()
        assert pool.checkedout() == held - 1

    async def test_scope_factory_opens_nothing_until_it_is_entered(self, client, _clean):
        # A handler depending on ScopeFactory has no transaction open while it waits on the AI
        # service — which is exactly what depending on Injected(...) would not give it.
        pool = container.engine.sync_engine.pool
        factory = ScopeFactory(container)

        idle = pool.checkedout()
        unopened = factory.open()
        assert pool.checkedout() == idle

        async with unopened as scope:
            assert await scope.resolve(AsyncSession).scalar(text("SELECT 1")) == 1

    async def test_a_scope_can_write_what_an_earlier_scope_read(self, client, _clean):
        # The read, close, call out, reopen, write shape, without the call.
        async with container.open_scope() as scope:
            category = await scope.resolve(IProductRepository).create_category("Split", "split")

        async with container.open_scope() as scope:
            from app.application.dtos.product_dto import ProductCreateDTO

            created = await scope.resolve(IProductRepository).create(
                ProductCreateDTO(
                    name="Written Later",
                    description="Created in a second transaction from a first one's result",
                    price=Decimal("9.99"),
                    stock=1,
                    category_id=category.id,
                )
            )

        assert created.category_slug == "split"
