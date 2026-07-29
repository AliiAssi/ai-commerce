from __future__ import annotations

import pytest

from app.application.search.normalizer import (
    detect_language,
    fold_for_matching,
    normalize,
    tokenize,
)


class TestNormalize:
    def test_the_original_query_survives_untouched(self):
        result = normalize("  Baladi EXTRA Virgin  ")

        assert result.original == "Baladi EXTRA Virgin"
        assert result.normalized == "baladi extra virgin"

    def test_repeated_whitespace_collapses(self):
        assert normalize("olive   oil\n\tfor  frying").normalized == "olive oil for frying"

    def test_latin_case_folds(self):
        assert normalize("TRIPOLI Soap").normalized == "tripoli soap"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("٠١٢٣٤٥٦٧٨٩", "0123456789"),  # Arabic-Indic
            ("۰۱۲۳۴۵۶۷۸۹", "0123456789"),  # Eastern Arabic-Indic
            ("تحت ٣٠ دولار", "تحت 30 دولار"),
        ],
    )
    def test_arabic_digits_become_ascii(self, raw: str, expected: str):
        # NFKC leaves these alone, so without an explicit table they never reach the number
        # parser and every Arabic budget phrase silently fails to apply.
        assert normalize(raw).normalized == expected

    def test_diacritics_and_tatweel_are_dropped(self):
        assert normalize("مُتَوَفِّر").normalized == "متوفر"
        assert normalize("صــــابون").normalized == "صابون"

    @pytest.mark.parametrize("raw", ["Za’atar", "Za‘atar", "Zaʼatar", "Za`atar"])
    def test_typographic_apostrophes_unify_to_ascii(self, raw: str):
        # The catalog spells it Za'atar with a plain apostrophe; a shopper's keyboard may not.
        assert normalize(raw).normalized == "za'atar"

    def test_the_apostrophe_itself_is_preserved(self):
        # §6 requires it: it is load-bearing in product names, so it folds rather than vanishes.
        assert "'" in normalize("Za'atar").normalized

    def test_query_is_not_truncated_here(self):
        # Length capping belongs to the parser, at the API edge; normalization stays pure.
        assert len(normalize("x" * 500).normalized) == 500


class TestLanguageDetection:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("olive oil under 25", "en"),
            ("زيت زيتون", "ar"),
            ("coffee من بيروت", "mixed"),
            ("", "en"),
            ("30", "en"),  # digits alone are not evidence of a language
            ("$25 !!", "en"),
        ],
    )
    def test_detection(self, text: str, expected: str):
        assert detect_language(text) == expected


class TestFolding:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("أقل", "اقل"),
            ("إلى", "الي"),
            ("آن", "ان"),
            ("مصنوعة", "مصنوعه"),
            ("مؤونة", "موونه"),
        ],
    )
    def test_orthographic_variants_fold(self, raw: str, expected: str):
        assert fold_for_matching(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "هدية للبيت مصنوعة يدوياً بأقل من ٣٠ دولار",
            "زيت زيتون للطبخ والقلي تحت ٢٥ دولار",
            "coffee من Beirut under 20",
            "أوعية خضراء للمقبلات",
        ],
    )
    def test_folding_preserves_length(self, raw: str):
        # This is what lets the parser match against the folded string and then slice spans out
        # of the unfolded one. A fold that changed length would silently corrupt every
        # semantic remainder.
        normalized = normalize(raw).normalized

        assert len(fold_for_matching(normalized)) == len(normalized)

    def test_folding_leaves_latin_alone(self):
        assert fold_for_matching("olive oil") == "olive oil"


class TestTokenize:
    def test_splits_on_punctuation_but_keeps_apostrophes(self):
        assert tokenize("za'atar, olive-oil") == ["za'atar", "olive", "oil"]

    def test_arabic_tokens(self):
        assert tokenize("زيت زيتون للطبخ") == ["زيت", "زيتون", "للطبخ"]

    def test_empty_text(self):
        assert tokenize("") == []

    def test_bare_punctuation_yields_nothing(self):
        assert tokenize("!!! ,. -") == []
