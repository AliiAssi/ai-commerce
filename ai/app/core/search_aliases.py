from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.application.search.normalizer import fold_for_matching

ALIASES_PATH = Path(__file__).with_name("search_aliases.yaml")

SORT_KEYS = ("price_asc", "price_desc", "rating", "newest")

# An alias is matched with word boundaries on both sides, plus two Arabic-specific allowances:
#
#  - a leading clitic cluster, because Arabic attaches prepositions and the article directly to
#    the word. "بطرابلس" is "in Tripoli" and must still find the alias "طرابلس"; "بأقل من" is
#    "at less than" and must find "أقل من".
#  - an optional trailing ha, which after folding is also ta marbuta. That makes "متوفرة" match
#    the alias "متوفر" without a second entry.
#
# Deliberately narrow. A general Arabic stemmer here would let "زيت" (oil) match "زيتون"
# (olives), which is the kind of quiet over-matching a filter must never do.
_AR_CLITICS = "وفبكل"  # waw fa ba kaf lam
_AR_PREFIX = f"(?:[{_AR_CLITICS}]{{0,2}}(?:ال)?)?"
_AR_SUFFIX = "ه?"  # ha; ta marbuta folds to this
_ARABIC_CHAR = re.compile("[؀-ۿ]")

# The number grammar, shared by the range templates below and by the parser's comparator
# matcher so the two can never drift. A USD marker on either side is absorbed into the match:
# the store is USD-only, so "$25", "25 usd" and "٢٥ دولار" are the same constraint, and leaving
# the word behind would strand "dollars" in the semantic text. Foreign currencies are handled
# earlier and separately — finding one suppresses the inference rather than consuming it.
_USD = r"(?:\$|usd|dollars?|دولارا?)"
NUMBER_PATTERN = rf"{_USD}?\s*(\d{{1,7}}(?:\.\d{{1,2}})?)\s*{_USD}?"


class AliasError(Exception):
    """The lexicon is unusable, or no longer describes the live catalog."""


def _is_arabic(text: str) -> bool:
    return _ARABIC_CHAR.search(text) is not None


def _alias_pattern(alias: str) -> str:
    """A regex for one alias phrase, tolerant of Arabic clitics and of extra whitespace."""
    words = [re.escape(word) for word in alias.split()]
    body = r"\s+".join(words)
    if _is_arabic(alias):
        return f"(?<!\\w){_AR_PREFIX}{body}{_AR_SUFFIX}(?!\\w)"
    return f"(?<!\\w){body}(?!\\w)"


@dataclass(frozen=True, slots=True)
class Alias:
    phrase: str  # folded, lowercase — what the pattern was built from
    pattern: re.Pattern[str]
    strong: bool


def _build_aliases(node: Any, *, strong: bool) -> list[Alias]:
    aliases: list[Alias] = []
    for language in ("en", "ar"):
        for raw in (node or {}).get(language) or []:
            phrase = fold_for_matching(str(raw).strip().casefold())
            if phrase:
                aliases.append(Alias(phrase, re.compile(_alias_pattern(phrase)), strong))
    return aliases


@dataclass(frozen=True, slots=True)
class Category:
    slug: str
    label: str
    aliases: tuple[Alias, ...]


@dataclass(slots=True)
class Place:
    key: str
    label: str
    # Literal products.origin strings this place owns. Empty for a pure region.
    origins: tuple[str, ...]
    children: tuple[str, ...]
    aliases: tuple[Alias, ...]
    # Filled in once the whole file is loaded: this place's origins plus every descendant's.
    resolved_origins: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class PriceLexicon:
    max_aliases: tuple[Alias, ...]
    min_aliases: tuple[Alias, ...]
    range_patterns: tuple[re.Pattern[str], ...]
    currency_pattern: re.Pattern[str]


class AliasLibrary:
    def __init__(
        self,
        *,
        version: int,
        weak_alias_max_extra_tokens: int,
        categories: dict[str, Category],
        places: dict[str, Place],
        price: PriceLexicon,
        availability: tuple[Alias, ...],
        sorts: dict[str, tuple[Alias, ...]],
    ) -> None:
        self.version = version
        self.weak_alias_max_extra_tokens = weak_alias_max_extra_tokens
        self.categories = categories
        self.places = places
        self.price = price
        self.availability = availability
        self.sorts = sorts

    def place(self, key: str) -> Place | None:
        return self.places.get(key)

    def origins_for(self, key: str) -> tuple[str, ...]:
        place = self.places.get(key)
        return () if place is None else place.resolved_origins

    def label_for_place(self, key: str) -> str:
        place = self.places.get(key)
        return key if place is None else place.label

    def label_for_category(self, slug: str) -> str:
        category = self.categories.get(slug)
        return slug if category is None else category.label

    # Startup guard. A category renamed in the admin, or a new origin appearing in the catalog,
    # silently narrows or breaks every query that used to resolve it — this is the check that
    # turns that into a loud failure instead of a slow relevance regression.
    def validate_against_catalog(
        self, *, category_slugs: Iterable[str], origins: Iterable[str]
    ) -> None:
        catalog_slugs = set(category_slugs)
        catalog_origins = {origin for origin in origins if origin}
        problems: list[str] = []

        unknown = sorted(set(self.categories) - catalog_slugs)
        if unknown:
            problems.append(f"lexicon names categories the catalog does not have: {unknown}")
        uncovered = sorted(catalog_slugs - set(self.categories))
        if uncovered:
            problems.append(f"catalog categories missing from the lexicon: {uncovered}")

        claimed = {origin for place in self.places.values() for origin in place.origins}
        stale = sorted(claimed - catalog_origins)
        if stale:
            problems.append(f"lexicon names origins the catalog does not have: {stale}")
        orphaned = sorted(catalog_origins - claimed)
        if orphaned:
            problems.append(f"catalog origins claimed by no place: {orphaned}")

        if problems:
            raise AliasError(
                f"{ALIASES_PATH.name} no longer describes the catalog:\n  " + "\n  ".join(problems)
            )


def _resolve_origins(places: dict[str, Place]) -> None:
    def walk(key: str, seen: set[str]) -> Iterator[str]:
        if key in seen:
            return  # a cycle in the hierarchy is a lexicon bug, not a reason to hang
        seen.add(key)
        place = places.get(key)
        if place is None:
            raise AliasError(f"place {key!r} lists an unknown child")
        yield from place.origins
        for child in place.children:
            yield from walk(child, seen)

    for key, place in places.items():
        # dict.fromkeys keeps declaration order, which keeps the generated SQL stable.
        place.resolved_origins = tuple(dict.fromkeys(walk(key, set())))


def _load_places(raw: dict[str, Any]) -> dict[str, Place]:
    places: dict[str, Place] = {}
    for key, node in (raw or {}).items():
        places[key] = Place(
            key=key,
            label=str(node.get("label", key)),
            origins=tuple(node.get("origins") or ()),
            children=tuple(node.get("children") or ()),
            aliases=tuple(
                _build_aliases(node.get("strong"), strong=True)
                + _build_aliases(node.get("weak"), strong=False)
            ),
        )
    for key, place in places.items():
        for child in place.children:
            if child not in places:
                raise AliasError(f"place {key!r} lists unknown child {child!r}")
    _resolve_origins(places)
    return places


def _load_price(raw: dict[str, Any]) -> PriceLexicon:
    templates = []
    for template in raw.get("range") or []:
        # Folded and case-folded like every other entry, or an Arabic template written in
        # ordinary orthography ("إلى") could never match the folded query text ("الي").
        folded = fold_for_matching(str(template).casefold())
        # Whitespace is optional so "و٢٥" — the Arabic conjunction fused to its number — still
        # parses, and the bounds are captured in template order.
        pattern = re.escape(folded).replace(r"\ ", r"\s*")
        pattern = pattern.replace(re.escape("{a}"), NUMBER_PATTERN).replace(
            re.escape("{b}"), NUMBER_PATTERN
        )
        templates.append(re.compile(f"(?<!\\w){pattern}(?!\\w)"))

    currencies = raw.get("foreign_currencies") or {}
    tokens = [
        re.escape(fold_for_matching(str(token).casefold()))
        for group in ("en", "ar")
        for token in currencies.get(group) or []
    ]
    symbols = [re.escape(str(symbol)) for symbol in currencies.get("symbols") or []]
    # Symbols carry no word boundary of their own; words do.
    parts = [f"(?<!\\w)(?:{'|'.join(tokens)})(?!\\w)"] if tokens else []
    if symbols:
        parts.append(f"(?:{'|'.join(symbols)})")

    return PriceLexicon(
        max_aliases=tuple(_build_aliases(raw.get("max"), strong=True)),
        min_aliases=tuple(_build_aliases(raw.get("min"), strong=True)),
        range_patterns=tuple(templates),
        currency_pattern=re.compile("|".join(parts) if parts else r"(?!x)x"),
    )


def load_aliases(path: Path = ALIASES_PATH) -> AliasLibrary:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AliasError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AliasError(f"{path.name} must be a mapping")

    categories = {
        slug: Category(
            slug=slug,
            label=str(node.get("label", slug)),
            aliases=tuple(
                _build_aliases(node.get("strong"), strong=True)
                + _build_aliases(node.get("weak"), strong=False)
            ),
        )
        for slug, node in (raw.get("categories") or {}).items()
    }
    if not categories:
        raise AliasError(f"{path.name} defines no categories")

    price_node = dict(raw.get("price") or {})
    price_node["foreign_currencies"] = raw.get("foreign_currencies")

    sorts = {
        key: tuple(_build_aliases((raw.get("sort") or {}).get(key), strong=True))
        for key in SORT_KEYS
    }
    missing = [key for key, aliases in sorts.items() if not aliases]
    if missing:
        raise AliasError(f"{path.name} has no sort phrases for: {', '.join(missing)}")

    return AliasLibrary(
        version=int(raw.get("version", 0)),
        weak_alias_max_extra_tokens=int(raw.get("weak_alias_max_extra_tokens", 2)),
        categories=categories,
        places=_load_places(raw.get("places") or {}),
        price=_load_price(price_node),
        availability=tuple(
            _build_aliases((raw.get("availability") or {}).get("strong"), strong=True)
        ),
        sorts=sorts,
    )


def load_aliases_or_exit(path: Path = ALIASES_PATH) -> AliasLibrary:
    try:
        return load_aliases(path)
    except AliasError as exc:
        sys.exit(f"FATAL: {exc}")
