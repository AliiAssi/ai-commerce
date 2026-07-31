from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.relevance_dto import (
    FAILURE_EMPTY,
    FAILURE_ERROR_EXPECTED,
    FAILURE_ERROR_UNEXPECTED,
    FAILURE_EXCLUDED,
    FAILURE_FILTERS,
    FAILURE_FIRST,
    FAILURE_INFERRED,
    FAILURE_MISSING,
    FAILURE_NOT_FIRST,
    FAILURE_UNKNOWN_PRODUCT,
    CaseResultDTO,
    LanguageScoreDTO,
    RelevanceReportDTO,
)
from app.application.dtos.search_dto import EffectiveFilters, ExplicitFilters, SearchQuery
from app.application.iservices.irelevance_service import IRelevanceService
from app.application.iservices.isearch_service import ISearchService
from app.application.search.metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank
from app.application.search.parser import IntentParser, resolve_filters
from app.core.container import ScopeFactory, open_scope
from app.core.exceptions import AppError
from app.core.index_state import IndexCoverage
from app.core.relevance import RelevanceCase, RelevanceCorpus
from app.core.search_aliases import AliasLibrary
from app.infrastructure.database.store_tables import products

logger = logging.getLogger(__name__)

GATE_EXACT_NAME = 1.0
GATE_FILTER_PRECISION = 1.0
GATE_RECALL_AT_5 = 0.90
GATE_MRR = 0.90

_NDCG_K = 10
_PAGE_SIZE = 20


class RelevanceService(IRelevanceService):
    def __init__(
        self,
        corpus: RelevanceCorpus,
        parser: IntentParser,
        aliases: AliasLibrary,
        coverage: IndexCoverage,
        scope_factory: ScopeFactory = open_scope,
    ) -> None:
        self._corpus = corpus
        self._parser = parser
        self._aliases = aliases
        self._coverage = coverage
        self._scope_factory = scope_factory

    async def score(
        self,
        *,
        label: str,
        include_drafts: bool = True,
        only: Sequence[str] | None = None,
    ) -> RelevanceReportDTO:
        catalog = await self._catalog()
        ready = self._coverage.ready
        selected = set(only) if only else None
        if selected:
            known = {case.id for case in self._corpus.cases}
            unknown = sorted(selected - known)
            if unknown:
                raise ValueError(f"unknown case id(s): {', '.join(unknown)}")

        results: list[CaseResultDTO] = []
        drafts: list[CaseResultDTO] = []
        for case in self._corpus.cases:
            if selected is not None and case.id not in selected:
                continue
            if not case.is_gate and not include_drafts:
                continue
            result = await self._run_case(case, catalog)
            (results if case.is_gate else drafts).append(result)

        overall = _score_group("overall", results)
        by_language = [
            _score_group(language, [r for r in results if r.language == language])
            for language in ("en", "ar", "mixed")
            if any(r.language == language for r in results)
        ]

        return RelevanceReportDTO(
            label=label,
            corpus_version=self._corpus.version,
            scored_cases=len(results),
            draft_cases=len(drafts),
            retrieval_path="documents (§12 step 3)" if ready else "catalog vector (§12 step 4)",
            index_coverage=(
                f"{self._coverage.documents}/{self._coverage.active_products}"
                if self._coverage.active_products
                else None
            ),
            overall=overall,
            by_language=by_language,
            results=results,
            drafts=drafts,
            gate_failures=_gate_failures(overall, by_language),
        )

    async def _run_case(self, case: RelevanceCase, catalog: dict[str, int]) -> CaseResultDTO:
        unknown = [name for name in case.product_names if name not in catalog]
        if unknown:
            return CaseResultDTO(
                case_id=case.id,
                language=case.language,
                source=case.source,
                query=case.query,
                passed=False,
                failures=[FAILURE_UNKNOWN_PRODUCT],
                detail=[f"catalog has no product named {name!r}" for name in unknown],
            )

        query = SearchQuery(
            q=case.query,
            explicit=ExplicitFilters(**_explicit(case)),
            page_size=_PAGE_SIZE,
        )

        try:
            async with self._scope_factory() as scope:
                result = await scope.resolve(ISearchService).search(query)
        except AppError as exc:
            if case.expect_error:
                return CaseResultDTO(
                    case_id=case.id,
                    language=case.language,
                    source=case.source,
                    query=case.query,
                    passed=True,
                )
            return CaseResultDTO(
                case_id=case.id,
                language=case.language,
                source=case.source,
                query=case.query,
                passed=False,
                failures=[FAILURE_ERROR_UNEXPECTED],
                detail=[f"{exc.__class__.__name__}: {exc}"],
            )

        if case.expect_error:
            return CaseResultDTO(
                case_id=case.id,
                language=case.language,
                source=case.source,
                query=case.query,
                passed=False,
                failures=[FAILURE_ERROR_EXPECTED],
                detail=["the query was answered when §9.3 requires it to be rejected"],
                total=result.total,
            )

        by_id = {product_id: name for name, product_id in catalog.items()}
        returned = [by_id.get(pid, str(pid)) for pid in result.product_ids]
        failures: list[str] = []
        detail: list[str] = []

        effective = self._effective_filters(case)
        self._check_filters(case, result, effective, failures, detail)
        self._check_ranking(case, result, catalog, returned, failures, detail)

        return CaseResultDTO(
            case_id=case.id,
            language=case.language,
            source=case.source,
            query=case.query,
            passed=not failures,
            failures=failures,
            detail=detail,
            reciprocal_rank=(
                reciprocal_rank(result.product_ids, catalog[case.first]) if case.first else None
            ),
            recall_at_k=(
                recall_at_k(
                    result.product_ids, [catalog[name] for name in case.required], case.top_k
                )
                if case.required
                else None
            ),
            ndcg_at_10=(
                ndcg_at_k(result.product_ids, _relevant_ids(case, catalog), _NDCG_K)
                if (case.required or case.first)
                else None
            ),
            filters_correct=(
                not _filter_mismatches(case, effective) if case.expect_filters else None
            ),
            exact_name_hit=(
                (bool(result.product_ids) and result.product_ids[0] == catalog[case.first])
                if case.exact_name and case.first
                else None
            ),
            returned=returned[: max(case.top_k, 5)],
            total=result.total,
            mode=result.mode,
            degraded_reason=result.degraded_reason,
        )

    def _effective_filters(self, case: RelevanceCase) -> EffectiveFilters:
        intent = self._parser.parse(case.query)
        return resolve_filters(intent, self._aliases, explicit=ExplicitFilters(**_explicit(case)))

    def _check_filters(
        self, case: RelevanceCase, result: Any, effective: EffectiveFilters, failures, detail
    ) -> None:
        mismatches = _filter_mismatches(case, effective)
        if mismatches:
            failures.append(FAILURE_FILTERS)
            detail.extend(mismatches)

        for name, expected in case.expect_inferred.items():
            actual = result.inferred_filters.get(name)
            if actual != expected:
                failures.append(FAILURE_INFERRED)
                detail.append(f"inferred {name}: expected {expected!r}, reported {actual!r}")

    def _check_ranking(
        self, case: RelevanceCase, result: Any, catalog, returned, failures, detail
    ) -> None:
        ids = result.product_ids

        if case.allow_empty and ids:
            failures.append(FAILURE_EMPTY)
            detail.append(f"expected no results, got {len(ids)}: {returned[:5]}")

        if case.first:
            wanted = catalog[case.first]
            if not ids or ids[0] != wanted:
                failures.append(FAILURE_FIRST)
                got = returned[0] if returned else "nothing"
                detail.append(f"expected {case.first!r} first, got {got!r}")

        for name in case.not_first:
            if ids and ids[0] == catalog[name]:
                failures.append(FAILURE_NOT_FIRST)
                detail.append(f"{name!r} must not rank first")

        window = set(ids[: case.top_k])
        missing = [name for name in case.required if catalog[name] not in window]
        if missing:
            failures.append(FAILURE_MISSING)
            for name in missing:
                position = ids.index(catalog[name]) + 1 if catalog[name] in ids else None
                where = f"rank {position}" if position else "absent"
                detail.append(f"required {name!r} not in top {case.top_k} ({where})")

        present = [name for name in case.excluded if catalog[name] in set(ids)]
        if present:
            failures.append(FAILURE_EXCLUDED)
            detail.extend(f"excluded {name!r} was returned" for name in present)

    async def _catalog(self) -> dict[str, int]:
        async with self._scope_factory() as scope:
            session = scope.resolve(AsyncSession)
            rows = (await session.execute(select(products.c.name, products.c.id))).all()
        return {row.name: row.id for row in rows}


def _explicit(case: RelevanceCase) -> dict[str, Any]:
    values = dict(case.explicit)
    if case.sort:
        values["sort"] = case.sort
    return values


def _relevant_ids(case: RelevanceCase, catalog: dict[str, int]) -> list[int]:
    names = list(case.required)
    if case.first:
        names.insert(0, case.first)
    return [catalog[name] for name in dict.fromkeys(names)]


def _filter_mismatches(case: RelevanceCase, effective: EffectiveFilters) -> list[str]:
    mismatches: list[str] = []
    for key, expected in case.expect_filters.items():
        actual = getattr(effective, key)
        if not _matches(expected, actual):
            mismatches.append(f"{key}: expected {expected!r}, applied {actual!r}")
    return mismatches


def _matches(expected: Any, actual: Any) -> bool:
    if actual is None:
        return False
    if isinstance(expected, bool):
        return bool(actual) is expected
    if isinstance(expected, Decimal):
        try:
            return Decimal(str(actual)) == expected
        except (ValueError, ArithmeticError):
            return False
    return str(actual) == str(expected)


def _score_group(language: str, results: list[CaseResultDTO]) -> LanguageScoreDTO:
    return LanguageScoreDTO(
        language=language,
        cases=len(results),
        passed=sum(1 for r in results if r.passed),
        mrr=mean([r.reciprocal_rank for r in results if r.reciprocal_rank is not None]),
        recall_at_5=mean([r.recall_at_k for r in results if r.recall_at_k is not None]),
        ndcg_at_10=mean([r.ndcg_at_10 for r in results if r.ndcg_at_10 is not None]),
        filter_precision=mean(
            [1.0 if r.filters_correct else 0.0 for r in results if r.filters_correct is not None]
        ),
        exact_name_rate=mean(
            [1.0 if r.exact_name_hit else 0.0 for r in results if r.exact_name_hit is not None]
        ),
    )


def _gate_failures(overall: LanguageScoreDTO, by_language: list[LanguageScoreDTO]) -> list[str]:
    failures: list[str] = []
    if overall.exact_name_rate < GATE_EXACT_NAME:
        failures.append(f"exact-name rate {overall.exact_name_rate:.2f} < {GATE_EXACT_NAME:.2f}")
    if overall.filter_precision < GATE_FILTER_PRECISION:
        failures.append(
            f"filter precision {overall.filter_precision:.2f} < {GATE_FILTER_PRECISION:.2f}"
        )
    if overall.mrr < GATE_MRR:
        failures.append(f"MRR {overall.mrr:.2f} < {GATE_MRR:.2f}")
    for score in [overall, *by_language]:
        if score.recall_at_5 < GATE_RECALL_AT_5:
            failures.append(
                f"recall@5 ({score.language}) {score.recall_at_5:.2f} < {GATE_RECALL_AT_5:.2f}"
            )
    return failures
