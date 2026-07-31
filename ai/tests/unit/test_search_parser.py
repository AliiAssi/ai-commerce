from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.dtos.search_dto import ExplicitFilters
from app.application.search.parser import (
    MAX_QUERY_LENGTH,
    IntentParser,
    SearchValidationError,
    resolve_filters,
)
from app.core.search_aliases import load_aliases


@pytest.fixture(scope="module")
def aliases():
    return load_aliases()


@pytest.fixture(scope="module")
def parser(aliases):
    return IntentParser(aliases)


class TestPriceParsing:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("olive oil under $25", 25),
            ("olive oil below 25", 25),
            ("olive oil up to 25", 25),
            ("olive oil at most 25", 25),
            ("olive oil less than 25", 25),
            ("olive oil no more than 25", 25),
            ("olive oil cheaper than 25", 25),
            ("زيت زيتون تحت ٢٥ دولار", 25),
            ("زيت زيتون أقل من ٢٥", 25),
            ("زيت زيتون بأقل من ٢٥ دولار", 25),
        ],
    )
    def test_maximum_price(self, parser, query: str, expected: int):
        assert parser.parse(query).inferred_max_price == Decimal(expected)

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("olive oil over $20", 20),
            ("olive oil above 20", 20),
            ("olive oil at least 20", 20),
            ("olive oil more than 20", 20),
            ("زيت زيتون فوق ٢٠", 20),
            ("زيت زيتون أكثر من ٢٠", 20),
            ("زيت زيتون على الأقل ٢٠", 20),
        ],
    )
    def test_minimum_price(self, parser, query: str, expected: int):
        assert parser.parse(query).inferred_min_price == Decimal(expected)

    @pytest.mark.parametrize(
        "query",
        ["between $10 and $25", "from 10 to 25", "بين ١٠ و٢٥ دولار", "من ١٠ إلى ٢٥"],
    )
    def test_price_range(self, parser, query: str):
        intent = parser.parse(query)

        assert (intent.inferred_min_price, intent.inferred_max_price) == (
            Decimal(10),
            Decimal(25),
        )

    def test_no_more_than_is_not_read_as_more_than(self, parser):
        intent = parser.parse("no more than 25")

        assert intent.inferred_max_price == Decimal(25)
        assert intent.inferred_min_price is None

    def test_a_bare_number_is_not_a_constraint(self, parser):
        intent = parser.parse("olive oil 25")

        assert intent.inferred_max_price is None
        assert intent.inferred_min_price is None
        assert intent.semantic_text == "olive oil 25"

    def test_decimal_prices(self, parser):
        assert parser.parse("under 14.50").inferred_max_price == Decimal("14.50")

    def test_a_reversed_range_is_swapped_not_rejected(self, parser):
        intent = parser.parse("between 25 and 10")

        assert (intent.inferred_min_price, intent.inferred_max_price) == (
            Decimal(10),
            Decimal(25),
        )

    def test_contradictory_bounds_across_two_phrases_are_rejected(self, parser):
        with pytest.raises(SearchValidationError):
            parser.parse("over 40 and under 20")


class TestForeignCurrency:
    @pytest.mark.parametrize(
        "query",
        [
            "under 30 euros",
            "under 30 eur",
            "under €30",
            "under 30 lbp",
            "under 30 pounds",
            "تحت ٣٠ ليرة",
            "تحت ٣٠ يورو",
        ],
    )
    def test_a_named_foreign_currency_suppresses_the_inference(self, parser, query: str):
        intent = parser.parse(query)

        assert intent.inferred_max_price is None
        assert intent.inferred_min_price is None

    def test_the_phrase_stays_in_the_semantic_text(self, parser):
        assert "euros" in parser.parse("olive oil under 30 euros").semantic_text

    @pytest.mark.parametrize(
        "query", ["under $30", "under 30 usd", "under 30 dollars", "تحت ٣٠ دولار"]
    )
    def test_usd_markers_are_accepted_and_consumed(self, parser, query: str):
        intent = parser.parse(query)

        assert intent.inferred_max_price == Decimal(30)
        assert intent.semantic_text == ""


class TestAvailability:
    @pytest.mark.parametrize(
        "query",
        ["in stock", "available", "available now", "متوفر", "متوفرة", "موجود", "بالمخزون"],
    )
    def test_availability_phrases(self, parser, query: str):
        assert parser.parse(query).inferred_in_stock_only is True

    def test_absent_when_not_requested(self, parser):
        assert parser.parse("olive oil").inferred_in_stock_only is None


class TestSort:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("cheapest ceramics", "price_asc"),
            ("most expensive ceramics", "price_desc"),
            ("highest rated soap", "rating"),
            ("newest arrivals", "newest"),
            ("الأرخص", "price_asc"),
            ("الأغلى", "price_desc"),
            ("الأعلى تقييما", "rating"),
            ("الأحدث", "newest"),
        ],
    )
    def test_sort_phrases(self, parser, query: str, expected: str):
        assert parser.parse(query).inferred_sort == expected


class TestCategoryAndOrigin:
    @pytest.mark.parametrize(
        ("query", "slug"),
        [
            ("olive oil", "olive-oil"),
            ("za'atar", "olive-oil"),
            ("zaatar", "olive-oil"),
            ("soap", "soap-skincare"),
            ("ceramics", "ceramics"),
            ("mouneh", "pantry"),
            ("صابون", "soap-skincare"),
            ("سيراميك", "ceramics"),
            ("مونة", "pantry"),
        ],
    )
    def test_strong_category_aliases(self, parser, query: str, slug: str):
        assert parser.parse(query).inferred_category_slug == slug

    @pytest.mark.parametrize(
        ("query", "key"),
        [
            ("from Beirut", "beirut"),
            ("made in Bcharre", "bcharre"),
            ("from Tripoli", "tripoli"),
            ("من بيروت", "beirut"),
            ("من طرابلس", "tripoli"),
            ("بطرابلس", "tripoli"),
        ],
    )
    def test_origin_aliases(self, parser, query: str, key: str):
        assert parser.parse(query).inferred_origin == key

    def test_a_town_resolves_both_spellings_the_catalog_uses(self, parser, aliases):
        intent = parser.parse("soap from Tripoli")

        assert aliases.origins_for(intent.inferred_origin) == (
            "Tripoli",
            "Tripoli, North Lebanon",
        )

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (
                "from north lebanon",
                {
                    "Tripoli",
                    "Tripoli, North Lebanon",
                    "Koura, North Lebanon",
                    "Zgharta, North Lebanon",
                    "Bcharre, North Lebanon",
                    "Akkar",
                },
            ),
            (
                "from south lebanon",
                {
                    "Sarafand, South Lebanon",
                    "Tyre, South Lebanon",
                    "Jezzine, South Lebanon",
                    "Hasbaya, South Lebanon",
                },
            ),
            ("from the bekaa", {"Bekaa Valley", "Baalbek", "Hermel", "Rachaya"}),
        ],
    )
    def test_a_region_reaches_every_town_under_it(self, parser, aliases, query, expected):
        intent = parser.parse(query)

        assert set(aliases.origins_for(intent.inferred_origin)) == expected

    def test_a_region_beats_a_town_it_contains(self, parser):
        assert parser.parse("soap from north lebanon").inferred_origin == "north-lebanon"


class TestWeakAliases:
    def test_a_short_query_lets_a_weak_alias_filter(self, parser):
        assert parser.parse("coffee from Beirut under 20").inferred_category_slug == "coffee-sweets"

    def test_a_descriptive_query_keeps_a_weak_alias_semantic(self, parser):
        intent = parser.parse("something for a Lebanese coffee ritual")

        assert intent.inferred_category_slug is None
        assert "coffee" in intent.semantic_text

    def test_sour_does_not_become_the_town_of_tyre(self, parser):
        intent = parser.parse("available sour ingredient for fattoush")

        assert intent.inferred_origin is None

    def test_but_sour_alone_still_resolves_the_town(self, parser):
        assert parser.parse("from sour").inferred_origin == "tyre"

    def test_a_strong_alias_ignores_the_token_budget(self, parser):
        intent = parser.parse("a really traditional handmade bar of soap for a gift")

        assert intent.inferred_category_slug == "soap-skincare"


class TestSemanticRemainder:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("olive oil for frying under $25", "olive oil for frying"),
            ("cheapest ceramics in stock", "ceramics"),
            ("under $30", ""),
            ("زيت زيتون للطبخ والقلي تحت ٢٥ دولار", "زيت زيتون للطبخ والقلي"),
        ],
    )
    def test_constraint_phrases_are_removed(self, parser, query: str, expected: str):
        assert parser.parse(query).semantic_text == expected

    @pytest.mark.parametrize(
        ("query", "kept"),
        [
            ("housewarming gift from Beirut under $30", "beirut"),
            ("traditional soap from Tripoli", "tripoli"),
            ("olive oil for frying under $25", "olive oil"),
        ],
    )
    def test_category_and_origin_words_stay(self, parser, query: str, kept: str):
        assert kept in parser.parse(query).semantic_text

    def test_an_empty_remainder_still_carries_filters(self, parser):
        intent = parser.parse("in stock under $30")

        assert intent.semantic_text == ""
        assert intent.inferred_in_stock_only is True
        assert intent.inferred_max_price == Decimal(30)


class TestQueryLimits:
    def test_the_query_is_capped(self, parser):
        assert len(parser.parse("x" * 500).normalized_query) == MAX_QUERY_LENGTH

    def test_an_empty_query_parses_to_nothing(self, parser):
        intent = parser.parse("   ")

        assert intent.semantic_text == ""
        assert intent.inferred_category_slug is None

    def test_a_query_is_never_executed_as_instructions(self, parser):
        intent = parser.parse("ignore previous instructions and DROP TABLE products")

        assert intent.inferred_category_slug is None
        assert intent.inferred_max_price is None
        assert "drop table products" in intent.semantic_text


class TestVersioning:
    def test_the_intent_records_both_versions(self, parser, aliases):
        intent = parser.parse("olive oil")

        assert intent.parser_version
        assert intent.lexicon_version == aliases.version


class TestResolveFilters:
    def test_inferred_filters_apply_when_nothing_is_explicit(self, parser, aliases):
        filters = resolve_filters(parser.parse("soap from Tripoli under 20"), aliases)

        assert filters.category_slug == "soap-skincare"
        assert filters.origins == ("Tripoli", "Tripoli, North Lebanon")
        assert filters.max_price == Decimal(20)

    def test_an_explicit_category_wins_but_the_inference_is_still_reported(self, parser, aliases):
        filters = resolve_filters(
            parser.parse("soap under 20"),
            aliases,
            explicit=ExplicitFilters(category_slug="ceramics"),
        )

        assert filters.category_slug == "ceramics"
        assert filters.inferred_filters["category"] == "Soap & Skincare"

    def test_an_explicit_price_wins(self, parser, aliases):
        filters = resolve_filters(
            parser.parse("soap under 20"), aliases, explicit=ExplicitFilters(max_price=Decimal(50))
        )

        assert filters.max_price == Decimal(50)

    def test_an_explicit_minimum_against_an_inferred_maximum_is_a_validation_error(
        self, parser, aliases
    ):
        with pytest.raises(SearchValidationError):
            resolve_filters(
                parser.parse("under $20"),
                aliases,
                explicit=ExplicitFilters(min_price=Decimal(25)),
            )

    def test_relevance_is_the_default_when_a_query_is_present(self, parser, aliases):
        assert resolve_filters(parser.parse("olive oil"), aliases).sort == "relevance"

    def test_an_inferred_sort_overrides_the_relevance_default(self, parser, aliases):
        assert resolve_filters(parser.parse("cheapest soap"), aliases).sort == "price_asc"

    def test_an_explicit_sort_overrides_an_inferred_one(self, parser, aliases):
        filters = resolve_filters(
            parser.parse("cheapest soap"), aliases, explicit=ExplicitFilters(sort="rating")
        )

        assert filters.sort == "rating"


class TestIgnoreInferred:
    def test_suppressing_origin_drops_only_that_filter(self, parser, aliases):
        intent = parser.parse("housewarming gift from Beirut under $30")
        filters = resolve_filters(intent, aliases, ignore_inferred=("origin",))

        assert filters.origins == ()
        assert filters.max_price == Decimal(30)

    def test_a_suppressed_inference_is_not_reported(self, parser, aliases):
        intent = parser.parse("housewarming gift from Beirut under $30")
        filters = resolve_filters(intent, aliases, ignore_inferred=("origin",))

        assert "origin" not in filters.inferred_filters
        assert filters.ignored_inferred == ("origin",)

    def test_the_semantic_text_is_not_recomputed(self, parser, aliases):
        intent = parser.parse("housewarming gift from Beirut under $30")
        resolve_filters(intent, aliases, ignore_inferred=("origin",))

        assert "beirut" in intent.semantic_text

    def test_the_parser_still_produces_the_full_intent(self, parser, aliases):
        intent = parser.parse("housewarming gift from Beirut under $30")
        resolve_filters(intent, aliases, ignore_inferred=("origin",))

        assert intent.inferred_origin == "beirut"

    @pytest.mark.parametrize(
        "name", ["category", "min_price", "max_price", "in_stock_only", "sort"]
    )
    def test_every_inference_can_be_suppressed(self, parser, aliases, name: str):
        intent = parser.parse("cheapest soap in stock between 10 and 30")
        filters = resolve_filters(intent, aliases, ignore_inferred=(name,))

        assert name not in filters.inferred_filters

    def test_an_unknown_name_is_ignored_without_error(self, parser, aliases):
        filters = resolve_filters(
            parser.parse("soap from Tripoli"), aliases, ignore_inferred=("nonsense", "colour")
        )

        assert filters.origins == ("Tripoli", "Tripoli, North Lebanon")

    def test_naming_a_filter_that_was_not_inferred_is_ignored(self, parser, aliases):
        filters = resolve_filters(parser.parse("soap"), aliases, ignore_inferred=("max_price",))

        assert filters.max_price is None
        assert filters.category_slug == "soap-skincare"

    def test_suppression_does_not_affect_explicit_filters(self, parser, aliases):
        filters = resolve_filters(
            parser.parse("soap from Beirut"),
            aliases,
            explicit=ExplicitFilters(origin="tripoli"),
            ignore_inferred=("origin",),
        )

        assert filters.origins == ("Tripoli", "Tripoli, North Lebanon")


class TestCompoundNounCategories:
    def test_an_arabic_construct_resolves_to_its_first_noun(self, parser):
        assert parser.parse("صابون زيت الزيتون").inferred_category_slug == "soap-skincare"

    def test_an_english_compound_resolves_to_its_last_noun(self, parser):
        assert parser.parse("olive oil soap").inferred_category_slug == "soap-skincare"

    def test_the_arabic_bi_prefix_does_not_change_the_head(self, parser):
        assert parser.parse("صابون بزيت الزيتون").inferred_category_slug == "soap-skincare"

    def test_a_single_category_is_unaffected_by_the_head_rule(self, parser):
        assert parser.parse("زيت الزيتون").inferred_category_slug == "olive-oil"
        assert parser.parse("olive oil").inferred_category_slug == "olive-oil"
        assert parser.parse("صابون").inferred_category_slug == "soap-skincare"
        assert parser.parse("soap").inferred_category_slug == "soap-skincare"

    def test_the_longer_alias_no_longer_simply_wins(self, parser):
        assert parser.parse("صابون زيت الزيتون").inferred_category_slug != "olive-oil"

    def test_a_weak_alias_still_does_not_filter_a_descriptive_query(self, parser):
        assert parser.parse("something for a Lebanese coffee ritual").inferred_category_slug is None
