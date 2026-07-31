from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.application.dtos.relevance_dto import LanguageScoreDTO, RelevanceReportDTO
from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.irelevance_service import IRelevanceService
from app.core.config import load_settings_or_exit
from app.core.container import container
from app.core.logging import setup_logging
from app.core.registry import configure, configure_relevance
from app.core.relevance import load_corpus

HARD_SET = (
    "ar-tea",
    "ar-gift-for-a-new-home",
    "ar-something-for-breakfast",
    "en-gift-for-a-cook",
    "en-natural-sweetener",
    "en-something-for-breakfast",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="score_relevance",
        description="Score live retrieval against the §15 acceptance corpus.",
    )
    parser.add_argument(
        "--label",
        default="baseline",
        help="what is being scored, recorded in the report (e.g. an embedding model id)",
    )
    parser.add_argument(
        "--gates-only",
        action="store_true",
        help="skip the draft cases and score only what gates a release",
    )
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated case ids to score, instead of the whole corpus",
    )
    parser.add_argument(
        "--phase7",
        action="store_true",
        help="the 24 gating cases plus the 8-case hard set: the whole phase 7 decision in 32 calls",
    )
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    parser.add_argument(
        "--failures", action="store_true", help="print every failing case, not just a summary"
    )
    return parser


def _row(score: LanguageScoreDTO) -> str:
    return (
        f"  {score.language:<8} {score.cases:>3} cases  "
        f"pass {score.passed:>3}/{score.cases:<3}  "
        f"MRR {score.mrr:.2f}  R@5 {score.recall_at_5:.2f}  "
        f"nDCG@10 {score.ndcg_at_10:.2f}  filters {score.filter_precision:.2f}"
    )


def _print(report: RelevanceReportDTO, *, show_failures: bool) -> None:
    print(f"corpus v{report.corpus_version} — {report.label}")
    print(f"  {report.scored_cases} gating case(s), {report.draft_cases} draft(s)")
    coverage = f" (index {report.index_coverage})" if report.index_coverage else ""
    print(f"  retrieval: {report.retrieval_path}{coverage}")
    print()
    print(_row(report.overall))
    for score in report.by_language:
        print(_row(score))
    print()

    failing = [r for r in report.results if not r.passed]
    drafts_failing = [r for r in report.drafts if not r.passed]

    if show_failures:
        for result in failing:
            print(f"  FAIL {result.case_id}  ({result.language})  {result.query}")
            for line in result.detail:
                print(f"       {line}")
        for result in drafts_failing:
            print(f"  draft-miss {result.case_id}  ({result.language})  {result.query}")
            for line in result.detail:
                print(f"       {line}")
        if failing or drafts_failing:
            print()

    if report.gates_pass:
        print("§15 gates: PASS")
    else:
        print("§15 gates: FAIL")
        for failure in report.gate_failures:
            print(f"  - {failure}")
    if drafts_failing:
        print(
            f"({len(drafts_failing)} of {report.draft_cases} draft case(s) missed — "
            "drafts are unreviewed and never gate)"
        )


async def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)
    configure_relevance(container)
    assert container.engine is not None

    try:
        await container.resolve(IIndexService).refresh_coverage()
        only = [c.strip() for c in args.only.split(",") if c.strip()]
        if args.phase7:
            corpus = load_corpus()
            only = [case.id for case in corpus.cases if case.is_gate] + list(HARD_SET)
        report = await container.resolve(IRelevanceService).score(
            label=args.label,
            include_drafts=not args.gates_only,
            only=only or None,
        )
        if args.json:
            print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
        else:
            _print(report, show_failures=args.failures or not report.gates_pass)
        return 0 if report.gates_pass else 1
    finally:
        await container.engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
