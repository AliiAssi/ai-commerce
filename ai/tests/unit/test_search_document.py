from __future__ import annotations

import pytest

from app.application.dtos.index_dto import CatalogRowDTO
from app.application.search.document import (
    DOCUMENT_VERSION,
    build_document,
    build_document_text,
    document_hash,
)

ROW = CatalogRowDTO(
    product_id=1,
    name="Baladi Extra Virgin Olive Oil",
    category_name="Olive Oil & Za'atar",
    origin="Koura, North Lebanon",
    description="Cold-pressed within six hours of harvest.",
)


class TestFormat:
    def test_the_document_is_the_four_labelled_lines_in_order(self):
        # §7.1 fixes both the labels and the order. Changing either invalidates every stored
        # hash, which is what DOCUMENT_VERSION exists to force a rebuild for.
        assert build_document_text(
            name=ROW.name,
            category_name=ROW.category_name,
            origin=ROW.origin,
            description=ROW.description,
        ) == (
            "Name: Baladi Extra Virgin Olive Oil\n"
            "Category: Olive Oil & Za'atar\n"
            "Origin: Koura, North Lebanon\n"
            "Description: Cold-pressed within six hours of harvest."
        )

    @pytest.mark.parametrize("origin", [None, ""])
    def test_a_missing_origin_omits_the_line_rather_than_leaving_it_empty(self, origin):
        # An empty `Origin: ` line would put the bare label into the tsvector as a lexeme, and
        # it has to match the SQL twin's CASE, which produces nothing at all for these two.
        text = build_document_text(name="X", category_name="C", origin=origin, description="D")

        assert "Origin:" not in text
        assert text.split("\n") == ["Name: X", "Category: C", "Description: D"]

    def test_a_whitespace_origin_is_kept(self):
        # `if origin` is true for " ", and so is `origin <> ''` in SQL. This is not a useful
        # value; it is asserted because the two implementations have to agree on it.
        assert "Origin:  " in build_document_text(
            name="X", category_name="C", origin=" ", description="D"
        )

    def test_field_values_are_not_trimmed(self):
        # Deliberate: Python's str.strip() and Postgres's btrim() strip different character
        # sets, and the drift sweep compares a hash computed on each side. Raw concatenation is
        # the only form that is trivially equal in both.
        assert build_document_text(
            name=" X ", category_name="C", origin=None, description="D"
        ).startswith("Name:  X \n")


class TestHash:
    def test_the_same_fields_always_hash_the_same(self):
        assert document_hash("abc") == document_hash("abc")

    def test_the_hash_is_lowercase_hex_sha256(self):
        # It is compared against encode(sha256(...), 'hex'), which is lowercase and 64 chars.
        digest = document_hash("abc")
        assert len(digest) == 64
        assert digest == digest.lower()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("name", "Something Else"),
            ("category_name", "Mouneh & Pantry"),
            ("origin", "Batroun"),
            ("description", "A different description."),
        ],
    )
    def test_changing_a_semantic_field_changes_the_hash(self, field, value):
        # §10.3's semantic-field list. A field that did not move the hash would leave the index
        # answering with stale text until something unrelated happened to touch the product.
        changed = ROW.model_copy(update={field: value})

        assert build_document(changed).document_hash != build_document(ROW).document_hash

    def test_the_hash_does_not_depend_on_the_product_id(self):
        # Two products with identical text hash identically, and that is fine: the hash answers
        # "has this document changed", never "which product is this".
        other = ROW.model_copy(update={"product_id": 999})

        assert build_document(other).document_hash == build_document(ROW).document_hash


class TestBuild:
    def test_a_built_document_carries_its_version_and_source_fields(self):
        document = build_document(ROW)

        assert document.document_version == DOCUMENT_VERSION
        assert document.document_hash == document_hash(document.document_text)
        # The source fields ride along because the stored tsvectors are built per field, so
        # §7.4 can weight a product name above a category name. The flattened text alone
        # could not support that.
        assert document.name == ROW.name
        assert document.category_name == ROW.category_name
        assert document.description == ROW.description
