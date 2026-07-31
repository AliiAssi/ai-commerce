from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Language = Literal["en", "ar", "mixed"]

NORMALIZER_VERSION = "1"

_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

_APOSTROPHES = str.maketrans(
    dict.fromkeys("’‘‛´`ʼʻʽ′", "'"),
)

_ARABIC_MARKS = re.compile("[ـً-ْٓ-ٰٕۖ-ۭ]")

_ARABIC_CHARS = re.compile("[؀-ۿݐ-ݿࢠ-ࣿ]")
_LATIN_CHARS = re.compile(r"[a-z]")

_WHITESPACE = re.compile(r"\s+")

_ARABIC_FOLD = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ة": "ه",
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
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
    return text.translate(_ARABIC_FOLD)


def detect_language(text: str) -> Language:
    has_arabic = _ARABIC_CHARS.search(text) is not None
    has_latin = _LATIN_CHARS.search(text) is not None
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    return "en"


_TOKEN_SPLIT = re.compile(r"[^\w']+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token.strip("'") for token in _TOKEN_SPLIT.split(text) if token.strip("'")]
