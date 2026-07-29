from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml

CORPUS_PATH = Path(__file__).with_name("relevance_corpus.yaml")

CaseSource = Literal["spec", "draft"]
CaseLanguage = Literal["en", "ar", "mixed"]

_SOURCES = ("spec", "draft")
_LANGUAGES = ("en", "ar", "mixed")
_DEFAULT_TOP_K = 5

# Every key a case may carry. Unknown keys are an error rather than a shrug: a typo in `required`
# would otherwise silently drop an assertion and the corpus would report a gate it never checked.
_CASE_KEYS = frozenset(
    {
        "id",
        "query",
        "language",
        "source",
        "section",
        "explicit",
        "sort",
        "expect_filters",
        "expect_inferred",
        "first",
        "not_first",
        "exact_name",
        "required",
        "excluded",
        "top_k",
        "allow_empty",
        "expect_error",
        "note",
    }
)

_FILTER_KEYS = frozenset(
    {"category_slug", "origin_key", "min_price", "max_price", "in_stock_only", "sort"}
)


class CorpusError(Exception):
    """The relevance corpus is unusable."""


@dataclass(frozen=True, slots=True)
class RelevanceCase:
    """One judged query. Products are named, never id'd — see the corpus header for why."""

    id: str
    query: str
    language: CaseLanguage
    source: CaseSource
    section: str | None = None

    explicit: dict[str, Any] = field(default_factory=dict)
    sort: str | None = None

    expect_filters: dict[str, Any] = field(default_factory=dict)
    expect_inferred: dict[str, str] = field(default_factory=dict)

    first: str | None = None
    not_first: tuple[str, ...] = ()
    exact_name: bool = False
    required: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    top_k: int = _DEFAULT_TOP_K
    allow_empty: bool = False
    expect_error: str | None = None
    note: str | None = None

    @property
    def is_gate(self) -> bool:
        """Whether a failure here fails a release.

        Draft cases are reported but never gate. They were generated rather than judged, and a
        corpus that fails a release on an unreviewed expectation teaches everyone to ignore it.
        """
        return self.source == "spec"

    @property
    def product_names(self) -> tuple[str, ...]:
        names = [*self.required, *self.excluded, *self.not_first]
        if self.first:
            names.append(self.first)
        return tuple(dict.fromkeys(names))


@dataclass(frozen=True, slots=True)
class RelevanceCorpus:
    version: int
    cases: tuple[RelevanceCase, ...]

    def for_language(self, language: str) -> tuple[RelevanceCase, ...]:
        return tuple(case for case in self.cases if case.language == language)

    @property
    def product_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for case in self.cases:
            names.extend(case.product_names)
        return tuple(dict.fromkeys(names))


def _as_tuple(value: Any, *, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CorpusError(f"{where} must be a list")
    return tuple(str(item) for item in value)


def _as_filters(value: Any, *, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CorpusError(f"{where} must be a mapping")
    unknown = set(value) - _FILTER_KEYS
    if unknown:
        raise CorpusError(f"{where} has unknown filter(s): {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {}
    for key, raw in value.items():
        if key in ("min_price", "max_price"):
            try:
                out[key] = Decimal(str(raw))
            except InvalidOperation as exc:
                raise CorpusError(f"{where}.{key} is not a number: {raw!r}") from exc
        elif key == "in_stock_only":
            out[key] = bool(raw)
        else:
            out[key] = str(raw)
    return out


def _build_case(raw: Any, *, index: int) -> RelevanceCase:
    if not isinstance(raw, dict):
        raise CorpusError(f"case {index} is not a mapping")
    case_id = str(raw.get("id") or "").strip()
    if not case_id:
        raise CorpusError(f"case {index} has no id")

    unknown = set(raw) - _CASE_KEYS
    if unknown:
        raise CorpusError(f"case {case_id!r} has unknown key(s): {', '.join(sorted(unknown))}")

    language = str(raw.get("language") or "").strip()
    if language not in _LANGUAGES:
        raise CorpusError(
            f"case {case_id!r} has language {language!r}; expected one of {_LANGUAGES}"
        )
    source = str(raw.get("source") or "").strip()
    if source not in _SOURCES:
        raise CorpusError(f"case {case_id!r} has source {source!r}; expected one of {_SOURCES}")

    query = str(raw.get("query") or "")
    if not query.strip():
        raise CorpusError(f"case {case_id!r} has an empty query")

    case = RelevanceCase(
        id=case_id,
        query=query,
        language=language,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        section=str(raw["section"]) if raw.get("section") else None,
        explicit=_as_filters(raw.get("explicit"), where=f"case {case_id!r} explicit"),
        sort=str(raw["sort"]) if raw.get("sort") else None,
        expect_filters=_as_filters(
            raw.get("expect_filters"), where=f"case {case_id!r} expect_filters"
        ),
        expect_inferred={str(k): str(v) for k, v in (raw.get("expect_inferred") or {}).items()},
        first=str(raw["first"]) if raw.get("first") else None,
        not_first=_as_tuple(raw.get("not_first"), where=f"case {case_id!r} not_first"),
        exact_name=bool(raw.get("exact_name", False)),
        required=_as_tuple(raw.get("required"), where=f"case {case_id!r} required"),
        excluded=_as_tuple(raw.get("excluded"), where=f"case {case_id!r} excluded"),
        top_k=int(raw.get("top_k", _DEFAULT_TOP_K)),
        allow_empty=bool(raw.get("allow_empty", False)),
        expect_error=str(raw["expect_error"]) if raw.get("expect_error") else None,
        note=str(raw["note"]).strip() if raw.get("note") else None,
    )

    # A case that asserts nothing passes for free and hides the fact that it does.
    asserts = (
        case.first
        or case.not_first
        or case.required
        or case.excluded
        or case.expect_filters
        or case.expect_inferred
        or case.allow_empty
        or case.expect_error
    )
    if not asserts:
        raise CorpusError(f"case {case_id!r} asserts nothing")
    if case.expect_error and (case.first or case.required):
        raise CorpusError(
            f"case {case_id!r} expects an error and also expects results; §9.3 makes those "
            "mutually exclusive"
        )
    if case.top_k < 1:
        raise CorpusError(f"case {case_id!r} has top_k < 1")
    return case


def load_corpus(path: Path | None = None) -> RelevanceCorpus:
    target = path or CORPUS_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CorpusError(f"relevance corpus not found at {target}") from exc
    except yaml.YAMLError as exc:
        raise CorpusError(f"relevance corpus is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise CorpusError("relevance corpus must be a mapping")
    version = raw.get("version")
    if not isinstance(version, int):
        raise CorpusError("relevance corpus needs an integer `version`")

    entries = raw.get("cases")
    if not isinstance(entries, list) or not entries:
        raise CorpusError("relevance corpus has no cases")

    cases = tuple(_build_case(entry, index=i) for i, entry in enumerate(entries))
    duplicates = {case.id for case in cases if [c.id for c in cases].count(case.id) > 1}
    if duplicates:
        raise CorpusError(f"duplicate case id(s): {', '.join(sorted(duplicates))}")
    return RelevanceCorpus(version=version, cases=cases)


def load_corpus_or_exit() -> RelevanceCorpus:
    try:
        return load_corpus()
    except CorpusError as exc:
        sys.exit(f"FATAL: {exc}")
