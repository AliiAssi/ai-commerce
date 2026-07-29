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
        # §18.1 step 4 reports English and Arabic separately, which is only meaningful if both
        # actually have cases. An Arabic half that quietly emptied would show as a perfect score.
        corpus = load_corpus()

        assert len(corpus.for_language("en")) >= 5
        assert len(corpus.for_language("ar")) >= 5

    def test_every_spec_case_cites_its_section(self):
        # A gating case that cannot point at the requirement it enforces cannot be argued with
        # when it fails.
        for case in load_corpus().cases:
            if case.is_gate:
                assert case.section, f"{case.id} has no §15 section"

    def test_only_spec_cases_gate(self):
        # Drafts were generated rather than judged. Letting them fail a release would teach
        # everyone to ignore the corpus.
        for case in load_corpus().cases:
            assert case.is_gate == (case.source == "spec")


class TestValidation:
    def test_a_valid_file_parses(self, tmp_path):
        corpus = load_corpus(write(tmp_path, VALID))

        assert len(corpus.cases) == 1
        assert corpus.cases[0].id == "a-case"

    def test_a_case_that_asserts_nothing_is_rejected(self, tmp_path):
        # It would pass for ever and hide the fact that it checks nothing.
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
        # A typo in `required` would otherwise silently drop the assertion and the corpus would
        # report a gate it never checked.
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
        # §9.3 makes them mutually exclusive: a rejected query is not a fallback.
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
        # Two cases sharing an id makes a failing run impossible to trace back to a query.
        with pytest.raises(CorpusError, match="duplicate"):
            load_corpus(write(tmp_path, VALID + VALID.split("cases:")[1]))

    def test_a_missing_file_is_reported_clearly(self, tmp_path):
        with pytest.raises(CorpusError, match="not found"):
            load_corpus(tmp_path / "nope.yaml")
