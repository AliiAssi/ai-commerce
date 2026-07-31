from __future__ import annotations

import textwrap

import pytest

from app.core.relevance import CorpusError, load_corpus

VALID = """
version: 1
cases:
  - id: a-case
    query: olive oil
    language: en
    source: spec
    first: Baladi Extra Virgin Olive Oil
"""


def write(tmp_path, body: str):
    path = tmp_path / "corpus.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


class TestLoading:
    def test_the_shipped_corpus_loads(self):
        corpus = load_corpus()

        assert corpus.version >= 1
        assert corpus.cases

    def test_the_shipped_corpus_covers_both_languages_independently(self):
        corpus = load_corpus()

        assert len(corpus.for_language("en")) >= 5
        assert len(corpus.for_language("ar")) >= 5

    def test_every_spec_case_cites_its_section(self):
        for case in load_corpus().cases:
            if case.is_gate:
                assert case.section, f"{case.id} has no §15 section"

    def test_only_spec_cases_gate(self):
        for case in load_corpus().cases:
            assert case.is_gate == (case.source == "spec")


class TestValidation:
    def test_a_valid_file_parses(self, tmp_path):
        corpus = load_corpus(write(tmp_path, VALID))

        assert len(corpus.cases) == 1
        assert corpus.cases[0].id == "a-case"

    def test_a_case_that_asserts_nothing_is_rejected(self, tmp_path):
        with pytest.raises(CorpusError, match="asserts nothing"):
            load_corpus(
                write(
                    tmp_path,
                    """
                    version: 1
                    cases:
                      - id: empty
                        query: x
                        language: en
                        source: spec
                    """,
                )
            )

    def test_an_unknown_key_is_rejected(self, tmp_path):
        with pytest.raises(CorpusError, match="unknown key"):
            load_corpus(
                write(
                    tmp_path,
                    """
                    version: 1
                    cases:
                      - id: typo
                        query: x
                        language: en
                        source: spec
                        requried: [Thing]
                    """,
                )
            )

    def test_expecting_both_an_error_and_results_is_rejected(self, tmp_path):
        with pytest.raises(CorpusError, match="mutually exclusive"):
            load_corpus(
                write(
                    tmp_path,
                    """
                    version: 1
                    cases:
                      - id: both
                        query: x
                        language: en
                        source: spec
                        expect_error: validation
                        first: Thing
                    """,
                )
            )

    @pytest.mark.parametrize("field,value", [("language", "fr"), ("source", "guess")])
    def test_an_unknown_enum_is_rejected(self, tmp_path, field, value):
        with pytest.raises(CorpusError):
            load_corpus(
                write(
                    tmp_path,
                    VALID.replace(f"{field}: en", f"{field}: {value}").replace(
                        f"{field}: spec", f"{field}: {value}"
                    ),
                )
            )

    def test_duplicate_ids_are_rejected(self, tmp_path):
        with pytest.raises(CorpusError, match="duplicate"):
            load_corpus(write(tmp_path, VALID + VALID.split("cases:")[1]))

    def test_a_missing_file_is_reported_clearly(self, tmp_path):
        with pytest.raises(CorpusError, match="not found"):
            load_corpus(tmp_path / "nope.yaml")
