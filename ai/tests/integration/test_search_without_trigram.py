from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.search_dto import RetrievalRequest
from app.application.search.parser import IntentParser, resolve_filters
from app.core.container import container, open_scope
from app.core.search_aliases import AliasLibrary
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.repositories.search_repository import SearchCapabilities
from app.main import probe_search_capabilities

# Search against a database without pg_trgm.
#
# The extension is created by the *web* service's migrations, since the trigram indexes live on
# web's `products` table — so this service can be pointed at a database that does not have it,
# which is exactly what happened. `word_similarity` then does not exist and every text search
# raised, so the capability is settled at boot and the leg is simply left out of the query.

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def _execute(sql: str) -> None:
    async with open_scope() as scope:
        await scope.resolve(AsyncSession).execute(text(sql))


@pytest.fixture
async def without_trigram(app):
    """Drop pg_trgm for the duration of one test, then put it and its indexes back."""
    await _execute("DROP EXTENSION IF EXISTS pg_trgm CASCADE")
    yield
    await _execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    await _execute(
        "CREATE INDEX IF NOT EXISTS ix_products_name_trgm ON products USING gin (name gin_trgm_ops)"
    )
    await _execute(
        "CREATE INDEX IF NOT EXISTS ix_products_origin_trgm "
        "ON products USING gin (origin gin_trgm_ops)"
    )


@pytest.fixture(autouse=True)
def reset_capabilities():
    """Each test starts believing trigram works, as a freshly booted process would."""
    capabilities = container.resolve(SearchCapabilities)
    capabilities.trigram = True
    yield
    capabilities.trigram = True


async def _search(query: str):
    aliases = container.resolve(AliasLibrary)
    intent = IntentParser(aliases).parse(query)
    filters = resolve_filters(intent, aliases)
    async with open_scope() as scope:
        return await scope.resolve(ISearchRepository).retrieve(
            RetrievalRequest(
                semantic_text=intent.semantic_text,
                normalized_query=intent.normalized_query,
                filters=filters,
                page=1,
                page_size=10,
            )
        )


class TestProbe:
    async def test_it_finds_the_extension_when_installed(self, app, beit_catalog):
        async with open_scope() as scope:
            detected = await scope.resolve(ISearchRepository).detect_capabilities()

        assert detected.trigram is True

    async def test_it_reports_the_extension_missing(self, app, beit_catalog, without_trigram):
        async with open_scope() as scope:
            detected = await scope.resolve(ISearchRepository).detect_capabilities()

        assert detected.trigram is False

    async def test_startup_switches_the_leg_off(self, app, beit_catalog, without_trigram):
        await probe_search_capabilities()

        assert container.resolve(SearchCapabilities).trigram is False

    async def test_startup_leaves_the_leg_on_when_the_extension_is_there(self, app, beit_catalog):
        container.resolve(SearchCapabilities).trigram = False

        await probe_search_capabilities()

        assert container.resolve(SearchCapabilities).trigram is True


class TestSearchWithTheLegDisabled:
    """Once the probe has switched trigram off, the query must never mention it again."""

    @pytest.fixture(autouse=True)
    async def probed(self, app, beit_catalog, without_trigram):
        await probe_search_capabilities()

    async def test_a_text_search_still_succeeds(self):
        # The original defect: this raised UndefinedFunctionError and became a 500.
        result = await _search("olive oil")

        assert result.total > 0
        assert result.trigram_hits == 0

    async def test_the_lexical_leg_still_ranks(self):
        result = await _search("olive oil for frying under $25")

        assert result.product_ids
        assert result.lexical_hits > 0

    async def test_filters_still_apply(self, beit_catalog):
        result = await _search("housewarming gift under $30 from Bcharre")

        assert {beit_catalog[pid] for pid in result.product_ids} == {
            "Cedar Coasters, set of six",
            "Mountain Wildflower Honey",
            "Beeswax and Olive Candle",
        }

    async def test_an_arabic_query_still_resolves_its_filters(self, beit_catalog):
        result = await _search("صابون تقليدي من طرابلس")

        assert {beit_catalog[pid] for pid in result.product_ids} == {
            "Tripoli Olive Oil Soap",
            "Laurel and Olive Soap, aged nine months",
        }

    async def test_an_unmatchable_query_still_returns_nothing(self):
        # Degrading must not turn a miss into a browse of the whole catalog.
        result = await _search("zzzznotathing")

        assert result.total == 0

    async def test_transliterations_are_what_the_store_loses(self):
        # The honest cost, pinned so nobody assumes the degradation is free: this is the query
        # §7.2 added the trigram leg for, and without the extension it cannot be answered.
        result = await _search("rakweh")

        assert result.total == 0


class TestCapabilityIsActuallyInjected:
    async def test_the_repository_shares_the_container_instance(self, app, beit_catalog):
        # A `SearchCapabilities | None` parameter would not match the bound instance, so the
        # repository would quietly build its own and every switch-off would last one request.
        container.resolve(SearchCapabilities).trigram = False

        result = await _search("rakweh")

        assert result.trigram_hits == 0
        assert result.total == 0
