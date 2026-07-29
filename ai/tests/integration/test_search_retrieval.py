from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.application.dtos.search_dto import ExplicitFilters, RetrievalRequest
from app.application.iservices.iindex_service import IIndexService
from app.application.search.parser import IntentParser, resolve_filters
from app.core.container import container, open_scope
from app.core.index_state import IndexCoverage
from app.core.search_aliases import AliasLibrary
from app.infrastructure.irepositories.isearch_repository import ISearchRepository

# Retrieval against real PostgreSQL, over the real seeded catalog. The cases are drawn from the
# §15 acceptance corpus, restricted to what a phase-1 lexical + trigram ranker can be held to:
# no embedding model exists yet, so the Arabic cases here assert the deterministic filters they
# resolve rather than the ranking §15 will require once one does (§2.1).

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


# Every case below runs twice, once on each of §12's two lexical rungs.
#
# `catalog_vector` is step 4, web's generated products.search_vector. `documents` is step 3,
# this service's own weighted documents, which phase 4 made the default whenever index coverage
# allows. Both are live paths a shopper can land on — the second one degrades to the first
# whenever coverage drops — so a corpus that only ever exercised one of them would leave the
# other free to regress unnoticed. Running the same assertions against both is also what proves
# the switch itself cost no relevance.
@pytest.fixture(params=["catalog_vector", "documents"])
async def search(request, app, beit_catalog):
    """Run a query end to end and return (names in order, retrieval result)."""
    if request.param == "documents":
        service = container.resolve(IIndexService)
        await service.sweep()
        await service.drain(max_batches=50)
        await service.refresh_coverage()
        assert container.resolve(IndexCoverage).ready, "the document leg was not actually engaged"

    async def run(query: str, *, explicit=None, ignore_inferred=(), page=1, page_size=10):
        aliases = container.resolve(AliasLibrary)
        intent = IntentParser(aliases).parse(query)
        filters = resolve_filters(
            intent, aliases, explicit=explicit, ignore_inferred=ignore_inferred
        )
        async with open_scope() as scope:
            result = await scope.resolve(ISearchRepository).retrieve(
                RetrievalRequest(
                    semantic_text=intent.semantic_text,
                    normalized_query=intent.normalized_query,
                    filters=filters,
                    page=page,
                    page_size=page_size,
                )
            )
        return [beit_catalog[pid] for pid in result.product_ids], result

    return run


class TestEnglishCorpus:
    async def test_a_budget_narrows_to_the_everyday_oil(self, search):
        names, result = await search("olive oil for frying under $25")

        assert names[0] == "Everyday Cooking Olive Oil"
        # The finishing and first-press oils are both over $25 and must be filtered out, not
        # merely outranked.
        assert "Koura Valley First Press" not in names
        assert result.total == len(names)

    async def test_a_descriptive_query_reaches_across_categories(self, search):
        names, _ = await search("something for a Lebanese coffee ritual")

        # The Copper Coffee Set is in Glass & Copper. It is only reachable because "coffee" was
        # left as semantic text instead of becoming a category filter.
        assert "Lebanese Coffee with Cardamom" in names[:5]
        assert "Copper Coffee Set" in names[:5]

    async def test_exact_phrase_beats_a_partial_name_match(self, search):
        names, _ = await search("green bowls for a mezze table")

        assert names[0] == "Olive-Glaze Mezze Bowls, set of six"

    async def test_an_origin_resolves_both_catalog_spellings(self, search):
        names, _ = await search("traditional soap from Tripoli")

        # One soap is stored as "Tripoli, North Lebanon", the other as the same string; the
        # place has to reach both spellings or one of them disappears.
        assert set(names) == {"Tripoli Olive Oil Soap", "Laurel and Olive Soap, aged nine months"}

    async def test_origin_and_price_together(self, search):
        names, _ = await search("housewarming gift under $30 from Bcharre")

        assert set(names) == {
            "Cedar Coasters, set of six",
            "Mountain Wildflower Honey",
            "Beeswax and Olive Candle",
        }

    async def test_availability_excludes_the_sold_out_product(self, search):
        names, _ = await search("available sour ingredient for fattoush")

        assert names[0] == "Pomegranate Molasses"
        # Sumac is relevant and sold out; the availability constraint is deterministic.
        assert "Single-Origin Sumac" not in names

    async def test_a_region_reaches_its_towns(self, search):
        names, _ = await search("handmade recycled glass drinkware from south Lebanon")

        assert "Recycled Glass Pitcher" in names[:3]
        assert "Sarafand Hand-Blown Tumblers, set of four" in names[:3]

    async def test_an_exact_product_name_ranks_first(self, search):
        names, _ = await search("Baladi Extra Virgin Olive Oil")

        assert names[0] == "Baladi Extra Virgin Olive Oil"

    async def test_nonsense_returns_nothing(self, search):
        # §15.1's no-result guard: no unrelated neighbours, and no falling back to a browse.
        names, result = await search("zzzznotathing")

        assert names == []
        assert result.total == 0


class TestTrigramLeg:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("rakweh", "Hammered Copper Rakwe"),
            ("rakwe", "Hammered Copper Rakwe"),
            ("zaatar", "Wild Mountain Za'atar"),
            ("zatar", "Wild Mountain Za'atar"),
            ("freekeh", "Smoked Freekeh"),
            ("makdous", "Makdous, Stuffed Baby Aubergines"),
        ],
    )
    async def test_transliteration_variants_still_find_the_product(
        self, search, query: str, expected: str
    ):
        # The reason §7.2 has a trigram leg at all: full-text search misses these entirely
        # because the shopper's spelling and the catalog's differ by a character or two.
        names, _ = await search(query)

        assert expected in names

    async def test_a_sold_out_product_is_still_findable(self, search):
        names, _ = await search("rakweh")

        assert "Hammered Copper Rakwe" in names


class TestFiltersOnly:
    async def test_a_query_of_pure_constraints_browses(self, search):
        names, result = await search("in stock under $10")

        assert result.filters_only is True
        assert names
        assert "Coarse Bulgur" in names

    async def test_an_arabic_query_still_applies_its_filters(self, search):
        # No Arabic text exists in the catalog, so neither lexical nor trigram can match
        # (§2.1). The deterministic filters are the whole answer until phase 6 adds vectors,
        # and returning them beats returning nothing.
        names, _ = await search("صابون تقليدي من طرابلس")

        assert set(names) == {"Tripoli Olive Oil Soap", "Laurel and Olive Soap, aged nine months"}

    async def test_an_arabic_query_combining_three_constraints(self, search):
        names, _ = await search("منتجات متوفرة من البقاع بأقل من ١٥ دولار")

        assert set(names) == {
            "Pomegranate Molasses",
            "Pickled Wild Cucumbers",
            "Coarse Bulgur",
            "Damascene Rose Water",
            "Wild Mountain Za'atar",
        }

    async def test_an_unmatched_query_with_no_filters_stays_empty(self, search):
        # The rule that keeps the constraint fallback from becoming "show everything".
        _, result = await search("zzzznotathing")

        assert result.total == 0


class TestSorting:
    async def test_an_explicit_sort_reorders_the_matched_set(self, search):
        names, result = await search("cheapest ceramics")

        assert names[0] == "Terracotta Herb Pot"  # $18.00, the cheapest in the category
        assert result.total == 6  # the whole category, not the whole catalog

    async def test_a_non_relevance_sort_does_not_widen_the_result_set(self, search):
        relevance, _ = await search("soap from Tripoli")
        by_price, _ = await search("soap from Tripoli", explicit=ExplicitFilters(sort="price_asc"))

        assert set(relevance) == set(by_price)
        assert by_price[0] == "Tripoli Olive Oil Soap"  # $9.00

    async def test_out_of_stock_ranks_below_an_equally_relevant_in_stock_product(self, search):
        # §5.3: visible by default, but it should not lead.
        names, _ = await search("copper")
        sold_out = names.index("Hammered Copper Rakwe")

        assert sold_out > 0


class TestPagination:
    async def test_pages_partition_the_result_set(self, search):
        first, result = await search("olive", page=1, page_size=3)
        second, _ = await search("olive", page=2, page_size=3)

        assert len(first) == 3
        assert set(first) & set(second) == set()
        assert result.total > 3

    async def test_the_total_counts_the_matched_set_not_the_page(self, search):
        _, result = await search("olive", page=1, page_size=2)

        assert result.total > result.page_size

    async def test_a_page_past_the_end_is_empty_but_the_total_holds(self, search):
        names, result = await search("olive", page=99, page_size=10)

        assert names == []
        assert result.total > 0


class TestFilterPrecedence:
    async def test_an_explicit_category_overrides_the_inferred_one(self, search):
        names, _ = await search("soap under 20", explicit=ExplicitFilters(category_slug="ceramics"))

        assert names
        assert "Tripoli Olive Oil Soap" not in names

    async def test_removing_an_inferred_origin_widens_the_result(self, search):
        narrow, _ = await search("housewarming gift under $30 from Bcharre")
        wide, _ = await search(
            "housewarming gift under $30 from Bcharre", ignore_inferred=("origin",)
        )

        # §5.2.1: Bcharre products stop being exclusive but the phrase still ranks them.
        assert set(narrow) < set(wide)

    async def test_an_explicit_price_replaces_the_inferred_one(self, search):
        names, _ = await search(
            "olive oil under $25", explicit=ExplicitFilters(max_price=Decimal(20))
        )

        assert "Baladi Extra Virgin Olive Oil" not in names  # $28.00


class TestArchivedProducts:
    async def test_archived_products_never_appear(self, search, archive_product):
        before, _ = await search("rakweh")
        assert "Hammered Copper Rakwe" in before

        await archive_product("Hammered Copper Rakwe")

        after, _ = await search("rakweh")
        assert "Hammered Copper Rakwe" not in after


class TestCatalogTerms:
    async def test_the_shipped_lexicon_describes_the_live_catalog(self, app, beit_catalog):
        # The same check main.py runs at startup, against real data rather than a fixture list.
        async with open_scope() as scope:
            terms = await scope.resolve(ISearchRepository).catalog_terms()

        container.resolve(AliasLibrary).validate_against_catalog(
            category_slugs=terms.category_slugs, origins=terms.origins
        )
