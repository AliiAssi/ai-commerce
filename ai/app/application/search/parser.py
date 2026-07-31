from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.application.dtos.search_dto import (
    INFERRED_NAMES,
    EffectiveFilters,
    ExplicitFilters,
    SearchIntent,
    SortKey,
)
from app.application.search.normalizer import fold_for_matching, normalize, tokenize
from app.core.exceptions import AppError
from app.core.search_aliases import NUMBER_PATTERN, Alias, AliasLibrary

_TRAILING_NUMBER = re.compile(rf"\s*{NUMBER_PATTERN}")

PARSER_VERSION = "1"

MAX_QUERY_LENGTH = 200

_CURRENCY_WINDOW = 12

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "for", "of", "and", "or", "with", "in", "on", "to", "from", "at",
        "some", "something", "any", "me", "my", "i", "is", "are", "that", "this", "please",
        "من", "في", "على", "الى", "او", "و", "مع", "عن", "شي", "شيء", "لل", "ال",
    }
)  # fmt: skip


class SearchValidationError(AppError):
    status_code = 422
    code = "invalid_search"


@dataclass(frozen=True, slots=True)
class _Span:
    start: int
    end: int


def _overlaps(span: _Span, taken: list[_Span]) -> bool:
    return any(span.start < other.end and other.start < span.end for other in taken)


def _decimal(raw: str) -> Decimal | None:
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


class IntentParser:
    def __init__(self, aliases: AliasLibrary) -> None:
        self._aliases = aliases

    def parse(self, raw: str) -> SearchIntent:
        query = normalize(raw[:MAX_QUERY_LENGTH])
        folded = fold_for_matching(query.normalized)

        taken: list[_Span] = []

        min_price, max_price = self._parse_prices(folded, taken)
        in_stock = self._parse_availability(folded, taken)
        sort = self._parse_sort(folded, taken)

        semantic_text = self._strip(query.normalized, taken)
        category_slug = self._parse_category(folded, semantic_text)
        origin_key = self._parse_origin(folded, semantic_text)

        if min_price is not None and max_price is not None and min_price > max_price:
            raise SearchValidationError(
                f"The minimum price ({min_price}) is higher than the maximum ({max_price}).",
                details={"min_price": str(min_price), "max_price": str(max_price)},
            )

        return SearchIntent(
            original_query=query.original,
            normalized_query=query.normalized,
            language=query.language,
            semantic_text=semantic_text,
            inferred_category_slug=category_slug,
            inferred_origin=origin_key,
            inferred_min_price=min_price,
            inferred_max_price=max_price,
            inferred_in_stock_only=True if in_stock else None,
            inferred_sort=sort,
            parser_version=PARSER_VERSION,
            lexicon_version=self._aliases.version,
        )

    def _parse_prices(self, text: str, taken: list[_Span]) -> tuple[Decimal | None, Decimal | None]:
        for pattern in self._aliases.price.range_patterns:
            for match in pattern.finditer(text):
                span = _Span(*match.span())
                if _overlaps(span, taken) or self._names_foreign_currency(text, span):
                    continue
                low, high = _decimal(match.group(1)), _decimal(match.group(2))
                if low is None or high is None:
                    continue
                taken.append(span)
                return (low, high) if low <= high else (high, low)

        max_price = self._bounded_price(text, self._aliases.price.max_aliases, taken)
        min_price = self._bounded_price(text, self._aliases.price.min_aliases, taken)
        return min_price, max_price

    def _bounded_price(
        self, text: str, aliases: tuple[Alias, ...], taken: list[_Span]
    ) -> Decimal | None:
        for alias in sorted(aliases, key=lambda a: len(a.phrase), reverse=True):
            for match in alias.pattern.finditer(text):
                number = _TRAILING_NUMBER.match(text, match.end())
                if number is None:
                    continue
                span = _Span(match.start(), number.end())
                if _overlaps(span, taken) or self._names_foreign_currency(text, span):
                    continue
                value = _decimal(number.group(1))
                if value is None:
                    continue
                taken.append(span)
                return value
        return None

    def _names_foreign_currency(self, text: str, span: _Span) -> bool:
        window = text[max(0, span.start - _CURRENCY_WINDOW) : span.end + _CURRENCY_WINDOW]
        return self._aliases.price.currency_pattern.search(window) is not None

    def _parse_availability(self, text: str, taken: list[_Span]) -> bool:
        return self._first_match(text, self._aliases.availability, taken) is not None

    def _parse_sort(self, text: str, taken: list[_Span]) -> SortKey | None:
        for key, aliases in self._aliases.sorts.items():
            if self._first_match(text, aliases, taken) is not None:
                return key  # type: ignore[return-value]
        return None

    def _first_match(
        self, text: str, aliases: tuple[Alias, ...], taken: list[_Span]
    ) -> _Span | None:
        for alias in sorted(aliases, key=lambda a: len(a.phrase), reverse=True):
            match = alias.pattern.search(text)
            if match is None:
                continue
            span = _Span(*match.span())
            if _overlaps(span, taken):
                continue
            taken.append(span)
            return span
        return None

    def _parse_category(self, text: str, semantic_text: str) -> str | None:
        best: tuple[int, str] | None = None
        for slug, category in self._aliases.categories.items():
            match = self._best_alias(text, semantic_text, category.aliases)
            if match is not None and (best is None or match > best[0]):
                best = (match, slug)
        return None if best is None else best[1]

    def _parse_origin(self, text: str, semantic_text: str) -> str | None:
        best: tuple[int, str] | None = None
        for key, place in self._aliases.places.items():
            match = self._best_alias(text, semantic_text, place.aliases)
            if match is not None and (best is None or match > best[0]):
                best = (match, key)
        return None if best is None else best[1]

    def _best_alias(self, text: str, semantic_text: str, aliases: tuple[Alias, ...]) -> int | None:
        best: int | None = None
        for alias in aliases:
            if alias.pattern.search(text) is None:
                continue
            if not alias.strong and not self._weak_alias_applies(alias, semantic_text):
                continue
            if best is None or len(alias.phrase) > best:
                best = len(alias.phrase)
        return best

    def _weak_alias_applies(self, alias: Alias, semantic_text: str) -> bool:
        alias_tokens = set(tokenize(alias.phrase))
        extra = [
            token
            for token in tokenize(fold_for_matching(semantic_text))
            if token not in alias_tokens and token not in _STOPWORDS and not token.isdigit()
        ]
        return len(extra) <= self._aliases.weak_alias_max_extra_tokens

    @staticmethod
    def _strip(text: str, taken: list[_Span]) -> str:
        if not taken:
            return text
        keep: list[str] = []
        cursor = 0
        for span in sorted(taken, key=lambda s: s.start):
            keep.append(text[cursor : span.start])
            cursor = max(cursor, span.end)
        keep.append(text[cursor:])
        return re.sub(r"\s+", " ", " ".join(keep)).strip()


def resolve_filters(
    intent: SearchIntent,
    aliases: AliasLibrary,
    *,
    explicit: ExplicitFilters | None = None,
    ignore_inferred: tuple[str, ...] = (),
) -> EffectiveFilters:
    explicit = explicit or ExplicitFilters()
    suppressed = {name for name in ignore_inferred if name in INFERRED_NAMES}

    inferred: dict[str, str] = {}

    def take(name: str, value):
        if value is None or name in suppressed:
            return None
        inferred[name] = str(value)
        return value

    category = take("category", intent.inferred_category_slug)
    origin_key = take("origin", intent.inferred_origin)
    min_price = take("min_price", intent.inferred_min_price)
    max_price = take("max_price", intent.inferred_max_price)
    in_stock = take("in_stock_only", intent.inferred_in_stock_only)
    sort = take("sort", intent.inferred_sort)

    if "origin" in inferred:
        inferred["origin"] = aliases.label_for_place(inferred["origin"])
    if "category" in inferred:
        inferred["category"] = aliases.label_for_category(inferred["category"])

    effective_category = explicit.category_slug or category
    effective_origin_key = explicit.origin or origin_key
    effective_min = explicit.min_price if explicit.min_price is not None else min_price
    effective_max = explicit.max_price if explicit.max_price is not None else max_price
    effective_stock = (
        explicit.in_stock_only if explicit.in_stock_only is not None else bool(in_stock)
    )

    if effective_min is not None and effective_max is not None and effective_min > effective_max:
        raise SearchValidationError(
            f"The minimum price ({effective_min}) is higher than the maximum ({effective_max}).",
            details={"min_price": str(effective_min), "max_price": str(effective_max)},
        )

    if explicit.sort is not None:
        effective_sort: SortKey = explicit.sort
    elif sort is not None:
        effective_sort = sort  # type: ignore[assignment]
    elif intent.semantic_text or intent.normalized_query:
        effective_sort = "relevance"
    else:
        effective_sort = "newest"

    origins = aliases.origins_for(effective_origin_key) if effective_origin_key else ()

    return EffectiveFilters(
        category_slug=effective_category,
        origins=origins,
        origin_key=effective_origin_key,
        min_price=effective_min,
        max_price=effective_max,
        in_stock_only=effective_stock,
        sort=effective_sort,
        inferred_filters=inferred,
        ignored_inferred=tuple(sorted(suppressed)),
    )
