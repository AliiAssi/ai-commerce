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
        text = build_document_text(name="X", category_name="C", origin=origin, description="D")

        assert "Origin:" not in text
        assert text.split("\n") == ["Name: X", "Category: C", "Description: D"]

    def test_a_whitespace_origin_is_kept(self):
        assert "Origin:  " in build_document_text(
            name="X", category_name="C", origin=" ", description="D"
        )

    def test_field_values_are_not_trimmed(self):
        assert build_document_text(
            name=" X ", category_name="C", origin=None, description="D"
        ).startswith("Name:  X \n")


class TestHash:
    def test_the_same_fields_always_hash_the_same(self):
        assert document_hash("abc") == document_hash("abc")

    def test_the_hash_is_lowercase_hex_sha256(self):
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
        changed = ROW.model_copy(update={field: value})

        assert build_document(changed).document_hash != build_document(ROW).document_hash

    def test_the_hash_does_not_depend_on_the_product_id(self):
        other = ROW.model_copy(update={"product_id": 999})

        assert build_document(other).document_hash == build_document(ROW).document_hash


class TestBuild:
    def test_a_built_document_carries_its_version_and_source_fields(self):
        document = build_document(ROW)

        assert document.document_version == DOCUMENT_VERSION
        assert document.document_hash == document_hash(document.document_text)
        assert document.name == ROW.name
        assert document.category_name == ROW.category_name
        assert document.description == ROW.description
