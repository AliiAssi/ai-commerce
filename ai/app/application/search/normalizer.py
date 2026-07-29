from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

# Deterministic query normalization. Every function here is pure: no settings, no database, no
# provider. The parser and the alias matcher are only as testable as this layer is, and §6
# requires normalization to work without the chat LLM in the request path.
#
# Arabic literals are written as escapes throughout. Bidirectional text reorders itself in an
# editor, so a range like "٠-٩" is reviewable in a way the rendered characters are not.

Language = Literal["en", "ar", "mixed"]

NORMALIZER_VERSION = "1"

# Arabic-Indic (U+0660..) and Eastern Arabic-Indic (U+06F0..) digits. NFKC leaves both alone —
# they are not compatibility equivalents of ASCII digits — so a query like "under ٣٠
# dollars" written in Arabic numerals never reaches the number parser unless we convert it here.
_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

# Curly and typographic apostrophes fold to ASCII so a shopper typing "Za’atar" matches the
# catalog's "Za'atar". §6 requires the apostrophe itself to survive: it is load-bearing in
# product names, so it is unified rather than stripped.
_APOSTROPHES = str.maketrans(
    dict.fromkeys("’‘‛´`ʼʻʽ′", "'"),
)

# Tatweel (U+0640) plus the harakat/tanwin ranges and the superscript alef. Removed outright:
# they are presentational, optional in real input, and would otherwise make every alias in the
# file need a diacritized variant beside it.
_ARABIC_MARKS = re.compile("[ـً-ْٓ-ٰٕۖ-ۭ]")

# Arabic script proper. The presentation-form blocks are deliberately absent: NFKC has already
# collapsed them into this range by the time language detection runs.
_ARABIC_CHARS = re.compile("[؀-ۿݐ-ݿࢠ-ࣿ]")
_LATIN_CHARS = re.compile(r"[a-z]")

_WHITESPACE = re.compile(r"\s+")

# Orthographic variants that carry no meaning for matching: hamza seats, the two ya forms, and
# ta marbuta. Applied only when matching aliases, never to the text handed to retrieval, so the
# shopper's own spelling still reaches the ranker.
#
# Every entry maps one character to one character. That is what lets the parser match against
# the folded string and slice spans out of the unfolded one — the indices stay aligned.
_ARABIC_FOLD = str.maketrans(
    {
        "أ": "ا",  # alef with hamza above -> alef
        "إ": "ا",  # alef with hamza below -> alef
        "آ": "ا",  # alef with madda -> alef
        "ٱ": "ا",  # alef wasla -> alef
        "ى": "ي",  # alef maksura -> ya
        "ئ": "ي",  # ya with hamza -> ya
        "ؤ": "و",  # waw with hamza -> waw
        "ة": "ه",  # ta marbuta -> ha
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    # Kept verbatim for the URL and the search box: §5.1 requires the shopper's own words to
    # survive round-tripping, however aggressively we rewrite the working copy.
    original: str
    normalized: str
    language: Language


def normalize(raw: str) -> NormalizedQuery:
    text = unicodedata.normalize("NFKC", raw)
    text = text.translate(_APOSTROPHES)
    text = text.translate(_DIGITS)
    text = _ARABIC_MARKS.sub("", text)
    text = text.casefold()
    text = _WHITESPACE.sub(" ", text).strip()
    return NormalizedQuery(original=raw.strip(), normalized=text, language=detect_language(text))


def fold_for_matching(text: str) -> str:
    """Fold Arabic orthographic variants. Length-preserving, so spans stay comparable."""
    return text.translate(_ARABIC_FOLD)


def detect_language(text: str) -> Language:
    has_arabic = _ARABIC_CHARS.search(text) is not None
    has_latin = _LATIN_CHARS.search(text) is not None
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    # Digits and punctuation alone are not evidence of a language, and English is both the
    # catalog's language and the only one with a lexical safety net (§2.1).
    return "en"


_TOKEN_SPLIT = re.compile(r"[^\w']+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Word tokens, used for trigram candidates and for weak-alias confidence."""
    return [token.strip("'") for token in _TOKEN_SPLIT.split(text) if token.strip("'")]
