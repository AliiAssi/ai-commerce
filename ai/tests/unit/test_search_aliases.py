from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.core.search_aliases import AliasError, load_aliases

CATALOG_SLUGS = [
    "olive-oil",
    "pantry",
    "coffee-sweets",
    "ceramics",
    "soap-skincare",
    "textiles",
    "woodwork",
    "glass-copper",
]

CATALOG_ORIGINS = [
    "Akkar",
    "Baalbek",
    "Bcharre, North Lebanon",
    "Beirut",
    "Beit Chabab",
    "Bekaa Valley",
    "Chouf",
    "Deir el Qamar",
    "Hasbaya, South Lebanon",
    "Hermel",
    "Jabal Moussa",
    "Jezzine, South Lebanon",
    "Koura, North Lebanon",
    "Rachaya",
    "Sarafand, South Lebanon",
    "Tripoli",
    "Tripoli, North Lebanon",
    "Tyre, South Lebanon",
    "Zgharta, North Lebanon",
    "Zouk Mikael",
]


@pytest.fixture(scope="module")
def aliases():
    return load_aliases()


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "aliases.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


class TestShippedLexicon:
    def test_it_loads(self, aliases):
        assert aliases.version >= 1
        assert len(aliases.categories) == 8

    def test_it_describes_the_seeded_catalog(self, aliases):
        aliases.validate_against_catalog(category_slugs=CATALOG_SLUGS, origins=CATALOG_ORIGINS)

    def test_every_catalog_origin_has_an_owner(self, aliases):
        claimed = {origin for place in aliases.places.values() for origin in place.origins}

        assert claimed == set(CATALOG_ORIGINS)

    def test_every_place_resolves_to_at_least_one_origin(self, aliases):
        empty = [key for key in aliases.places if not aliases.origins_for(key)]

        assert empty == []

    def test_both_spellings_of_tripoli_resolve_together(self, aliases):
        assert aliases.origins_for("tripoli") == ("Tripoli", "Tripoli, North Lebanon")

    def test_a_region_resolves_to_its_descendants(self, aliases):
        assert aliases.origins_for("chouf") == ("Chouf", "Deir el Qamar")

    def test_labels_are_human_readable(self, aliases):
        assert aliases.label_for_place("north-lebanon") == "North Lebanon"
        assert aliases.label_for_category("olive-oil") == "Olive Oil & Za'atar"


class TestCatalogValidation:
    def test_a_renamed_category_fails_loudly(self, aliases):
        with pytest.raises(AliasError, match="missing from the lexicon"):
            aliases.validate_against_catalog(
                category_slugs=[*CATALOG_SLUGS[:-1], "glass-and-copper"],
                origins=CATALOG_ORIGINS,
            )

    def test_a_category_the_catalog_dropped_fails(self, aliases):
        with pytest.raises(AliasError, match="does not have"):
            aliases.validate_against_catalog(
                category_slugs=CATALOG_SLUGS[:-1], origins=CATALOG_ORIGINS
            )

    def test_a_new_origin_with_no_alias_fails(self, aliases):
        with pytest.raises(AliasError, match="claimed by no place"):
            aliases.validate_against_catalog(
                category_slugs=CATALOG_SLUGS, origins=[*CATALOG_ORIGINS, "Batroun"]
            )

    def test_an_origin_the_catalog_dropped_fails(self, aliases):
        with pytest.raises(AliasError, match="does not have"):
            aliases.validate_against_catalog(
                category_slugs=CATALOG_SLUGS, origins=CATALOG_ORIGINS[:-1]
            )

    def test_empty_origins_are_not_counted(self, aliases):
        with pytest.raises(AliasError, match="does not have"):
            aliases.validate_against_catalog(category_slugs=CATALOG_SLUGS, origins=["", None])


class TestLoaderErrors:
    def test_a_missing_file(self, tmp_path):
        with pytest.raises(AliasError, match="cannot read"):
            load_aliases(tmp_path / "absent.yaml")

    def test_malformed_yaml(self, tmp_path):
        with pytest.raises(AliasError, match="cannot read"):
            load_aliases(_write(tmp_path, "categories: [unclosed\n"))

    def test_no_categories(self, tmp_path):
        with pytest.raises(AliasError, match="no categories"):
            load_aliases(_write(tmp_path, "version: 1\nplaces: {}\n"))

    def test_an_unknown_child_place(self, tmp_path):
        body = """
        version: 1
        categories:
          soap-skincare:
            label: Soap
            strong: {en: [soap]}
        places:
          north-lebanon:
            label: North
            children: [nowhere]
        sort:
          price_asc: {en: [cheapest]}
          price_desc: {en: [priciest]}
          rating: {en: [top rated]}
          newest: {en: [newest]}
        """
        with pytest.raises(AliasError, match="unknown child"):
            load_aliases(_write(tmp_path, body))

    def test_missing_sort_phrases(self, tmp_path):
        body = """
        version: 1
        categories:
          soap-skincare:
            label: Soap
            strong: {en: [soap]}
        places: {}
        sort:
          price_asc: {en: [cheapest]}
        """
        with pytest.raises(AliasError, match="no sort phrases"):
            load_aliases(_write(tmp_path, body))
