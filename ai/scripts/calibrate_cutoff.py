from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.application.dtos.search_dto import (
    EffectiveFilters,
    QueryVectorDTO,
    RetrievalRequest,
)
from app.application.iservices.iindex_service import IIndexService
from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.llm.iembedding_client import EmbeddingError
from app.application.rerank.ireranker import IReranker, RerankCandidate
from app.application.search.parser import IntentParser
from app.core.config import get_settings
from app.core.container import container, open_scope
from app.core.registry import configure
from app.core.search_aliases import load_aliases_or_exit
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from tests.support.relevance import RelevanceCase, load_corpus_or_exit


async def _query_vector(intent, providers: EmbeddingProviders) -> QueryVectorDTO | None:
    """The semantic leg, without which an Arabic query retrieves nothing from an English catalog."""
    if not providers.any_configured or not intent.semantic_text:
        return None
    try:
        batch, slot = await providers.embed_query(intent.semantic_text)
    except EmbeddingError as exc:
        print(f"  embedding failed ({exc.code}); scoring the lexical candidates only")
        return None
    return QueryVectorDTO(
        values=batch.vectors[0],
        slot=slot,
        embedding_model=batch.model,
        dimensions=batch.dimensions,
    )


async def _score_case(
    case: RelevanceCase,
    parser: IntentParser,
    reranker: IReranker,
    providers: EmbeddingProviders,
    catalog: dict[int, str],
) -> tuple[list[float], list[float]]:
    intent = parser.parse(case.query)
    vector = await _query_vector(intent, providers)
    async with open_scope() as scope:
        repository = scope.resolve(ISearchRepository)

        result = await repository.retrieve(
            RetrievalRequest(
                semantic_text=intent.semantic_text,
                normalized_query=intent.normalized_query,
                filters=EffectiveFilters(),
                page=1,
                page_size=20,
                query_vector=vector,
            )
        )
        candidates: list[RerankCandidate] = await repository.rerank_candidates(result.product_ids)

    if len(candidates) < 2:
        return [], []

    rerank = await reranker.rerank(intent, candidates, window=get_settings().RERANKER_TOP_K)
    scores = [s for s in (rerank.scores or []) if s is not None]
    if not scores:
        print(f"  {case.id}: reranker returned no scores ({rerank.outcome})")
        return [], []

    wanted = set(case.relevant)
    relevant_scores: list[float] = []
    irrelevant_scores: list[float] = []
    for product_id, score in zip(rerank.product_ids, rerank.scores or [], strict=False):
        if score is None:
            continue
        (relevant_scores if catalog.get(product_id) in wanted else irrelevant_scores).append(score)

    top = ", ".join(
        f"{catalog.get(p, p)}={s:.4f}" for p, s in zip(rerank.product_ids, scores, strict=False)
    )
    print(f"  {case.id} [{case.language}] {case.query!r}\n    {top}")
    return relevant_scores, irrelevant_scores


async def main() -> None:
    parser_args = argparse.ArgumentParser(
        description="Dump live reranker scores for the relevance corpus so RERANK_MIN_SCORE "
        "and RERANK_MIN_SCORE_AR can be set from real numbers rather than guesses."
    )
    parser_args.add_argument("--language", choices=("en", "ar", "mixed"), action="append")
    args = parser_args.parse_args()

    settings = get_settings()
    if not settings.RERANKER_PROVIDER:
        sys.exit("FATAL: no RERANKER_PROVIDER configured; there is nothing to calibrate against.")

    configure(container, settings)
    aliases = load_aliases_or_exit()
    parser = IntentParser(aliases)
    reranker = container.resolve(IReranker)
    providers = container.resolve(EmbeddingProviders)

    # Without this the semantic leg is gated off and every query is scored against lexical
    # candidates only — which for Arabic against an English catalog means no candidates at all.
    await container.resolve(IIndexService).refresh_coverage()

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.infrastructure.database.store_tables import products

    async with open_scope() as scope:
        rows = (
            await scope.resolve(AsyncSession).execute(select(products.c.id, products.c.name))
        ).all()
    catalog = {row.id: row.name for row in rows}

    corpus = load_corpus_or_exit()
    languages = set(args.language or ("en", "ar", "mixed"))

    relevant: dict[str, list[float]] = {}
    irrelevant: dict[str, list[float]] = {}
    for case in corpus.cases:
        if case.language not in languages or not case.relevant:
            continue
        hits, misses = await _score_case(case, parser, reranker, providers, catalog)
        relevant.setdefault(case.language, []).extend(hits)
        irrelevant.setdefault(case.language, []).extend(misses)

    print(f"\nreranker: {reranker.version}\n")
    for language in sorted(relevant):
        hits = sorted(relevant[language])
        misses = sorted(irrelevant.get(language, []))
        if not hits:
            continue
        floor = statistics.quantiles(hits, n=20)[0] if len(hits) > 1 else hits[0]
        print(f"{language}:")
        print(
            f"  relevant   n={len(hits):3d} min={hits[0]:.4f} median={statistics.median(hits):.4f}"
        )
        if misses:
            print(
                f"  irrelevant n={len(misses):3d} max={misses[-1]:.4f} "
                f"median={statistics.median(misses):.4f}"
            )
        print(f"  -> a floor near {floor:.3f} keeps 95% of the relevant products\n")

    print(
        "Set RERANK_MIN_SCORE (en) and RERANK_MIN_SCORE_AR (ar/mixed) between the irrelevant\n"
        "maximum and the relevant minimum. Where those overlap, lean low and let\n"
        "RERANK_GAP_RATIO cut the tail instead — a floor that is too high empties good queries."
    )


if __name__ == "__main__":
    asyncio.run(main())
