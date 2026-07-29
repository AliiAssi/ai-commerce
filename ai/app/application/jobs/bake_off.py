from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.application.dtos.index_dto import CatalogRowDTO
from app.application.llm.gemini_embedding_client import GeminiEmbeddingClient
from app.application.llm.iembedding_client import EmbeddingError, IEmbeddingClient
from app.application.llm.openai_embedding_client import OpenAICompatibleEmbeddingClient
from app.application.search.document import build_document
from app.application.search.metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank
from app.application.search.parser import IntentParser, resolve_filters
from app.core.config import Settings, load_settings_or_exit
from app.core.container import container, open_scope
from app.core.logging import setup_logging
from app.core.registry import configure
from app.core.relevance import RelevanceCase, load_corpus_or_exit
from app.core.search_aliases import AliasLibrary
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.repositories.search_repository import filtered_products

# §18.1 step 3: embed the live catalog with each candidate and score it against the fixed corpus.
#
# Scored in memory rather than through pgvector, deliberately. §18.1 step 6 says to fix
# EMBEDDING_DIMENSIONS and build the HNSW index only *after* a winner is chosen, so the bake-off
# cannot depend on a schema that the bake-off's own outcome decides. Cosine over 46 vectors in
# Python is exact — no approximate index, no recall loss from ef_search — which makes this a
# measurement of the model rather than of the index built on it.
#
# What this measures is the SEMANTIC LEG ALONE, inside each case's deterministic filters. It is
# not comparable to the phase-4 baseline, which is lexical+trigram RRF; phase 6 measures the
# fused system. What it is comparable to is the same number for another candidate.

_NDCG_K = 10


@dataclass(frozen=True, slots=True)
class Candidate:
    provider: str
    model: str
    dimensions: int

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}@{self.dimensions}"


def _client(candidate: Candidate, settings: Settings) -> IEmbeddingClient:
    """Build a real adapter, exactly as the service would (§18.1 step 1)."""
    overrides = {
        "EMBEDDING_PROVIDER": candidate.provider,
        "EMBEDDING_MODEL": candidate.model,
        "EMBEDDING_DIMENSIONS": candidate.dimensions,
    }
    if candidate.provider == "gemini":
        tuned = settings.model_copy(
            update={
                **overrides,
                "EMBEDDING_HOST": "https://generativelanguage.googleapis.com",
                "EMBEDDING_API_KEY": os.environ.get("GEMINI_API_KEY", settings.EMBEDDING_API_KEY),
            }
        )
        return GeminiEmbeddingClient(tuned)
    tuned = settings.model_copy(
        update={
            **overrides,
            "EMBEDDING_HOST": "https://openrouter.ai",
            "EMBEDDING_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),
        }
    )
    return OpenAICompatibleEmbeddingClient(tuned)


def cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


async def _catalog() -> list[CatalogRowDTO]:
    async with open_scope() as scope:
        from sqlalchemy.ext.asyncio import AsyncSession

        session = scope.resolve(AsyncSession)
        rows = (
            await session.execute(
                select(
                    products.c.id,
                    products.c.name,
                    categories.c.name.label("category_name"),
                    products.c.origin,
                    products.c.description,
                )
                .select_from(products.join(categories, categories.c.id == products.c.category_id))
                .where(products.c.is_archived.is_(False))
            )
        ).all()
    return [
        CatalogRowDTO(
            product_id=r.id,
            name=r.name,
            category_name=r.category_name,
            origin=r.origin,
            description=r.description,
        )
        for r in rows
    ]


async def _eligible_ids(
    case: RelevanceCase, parser: IntentParser, aliases: AliasLibrary
) -> set[int]:
    """The products the case's deterministic filters leave standing.

    The semantic leg never overrules a filter (§7.3), so scoring it against the whole catalog
    would credit or blame the model for work SQL already did.
    """
    from app.application.dtos.search_dto import ExplicitFilters

    intent = parser.parse(case.query)
    explicit = dict(case.explicit)
    if case.sort:
        explicit["sort"] = case.sort
    filters = resolve_filters(intent, aliases, explicit=ExplicitFilters(**explicit))
    async with open_scope() as scope:
        from sqlalchemy.ext.asyncio import AsyncSession

        session = scope.resolve(AsyncSession)
        rows = (await session.execute(filtered_products(filters))).scalars().all()
    return set(rows)


async def _embed_query_paced(client: IEmbeddingClient, query: str):
    """One query embedding, retrying a rate limit rather than abandoning the run.

    A hundred-case corpus is a hundred sequential calls, and the free tier starts refusing
    part-way through — which failed a whole bake-off after it had already paid for the document
    batch. Only `retryable` codes wait; an unauthorized key or a malformed request fails fast,
    because retrying either just costs time to reach the same answer.
    """
    delay = 2.0
    for attempt in range(5):
        try:
            return await client.embed_query(query)
        except EmbeddingError as exc:
            if not exc.retryable or attempt == 4:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


async def score_candidate(candidate: Candidate, settings: Settings, corpus) -> dict:
    client = _client(candidate, settings)
    catalog = await _catalog()
    by_name = {row.name: row.product_id for row in catalog}

    documents = [build_document(row).document_text for row in catalog]
    started = time.perf_counter()
    batch = await client.embed_documents(documents)
    backfill_ms = (time.perf_counter() - started) * 1000
    vectors = dict(zip([row.product_id for row in catalog], batch.vectors, strict=True))

    parser = container.resolve(IntentParser)
    aliases = container.resolve(AliasLibrary)

    per_language: dict[str, list[tuple[float, float, float]]] = {}
    latencies: list[float] = []
    misses: list[str] = []

    for case in corpus.cases:
        if case.expect_error or case.allow_empty:
            continue
        if case.sort or case.expect_filters.get("sort"):
            # An explicit sort owns the ordering (§7.5), so cosine similarity cannot be scored
            # against it. `en-expensive-first` failed here purely because this harness ranks by
            # similarity and the case is about price_desc — a harness limit, not a model one.
            continue
        if not case.first and not case.required:
            continue
        if any(name not in by_name for name in case.product_names):
            continue

        eligible = await _eligible_ids(case, parser, aliases)
        started = time.perf_counter()
        query_batch = await _embed_query_paced(client, case.query)
        latencies.append((time.perf_counter() - started) * 1000)
        qv = query_batch.vectors[0]

        ranked = [
            pid
            for _, pid in sorted(
                ((cosine(qv, vectors[pid]), pid) for pid in eligible), reverse=True
            )
        ]
        rr = reciprocal_rank(ranked, by_name[case.first]) if case.first else 1.0
        rec = (
            recall_at_k(ranked, [by_name[n] for n in case.required], case.top_k)
            if case.required
            else 1.0
        )
        relevant = [
            by_name[n]
            for n in dict.fromkeys([*([case.first] if case.first else []), *case.required])
        ]
        nd = ndcg_at_k(ranked, relevant, _NDCG_K)
        per_language.setdefault(case.language, []).append((rr, rec, nd))
        if (case.first and rr < 1.0) or rec < 1.0:
            misses.append(f"{case.id} (rr={rr:.2f} r@k={rec:.2f})")

    everything = [m for values in per_language.values() for m in values]
    return {
        "candidate": candidate,
        "dimensions": batch.dimensions,
        "backfill_ms": backfill_ms,
        "query_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0.0,
        "overall": _summary(everything),
        "by_language": {lang: _summary(v) for lang, v in sorted(per_language.items())},
        "misses": misses,
    }


def _summary(rows: list[tuple[float, float, float]]) -> dict:
    return {
        "cases": len(rows),
        "mrr": mean([r for r, _, _ in rows]),
        "recall": mean([r for _, r, _ in rows]),
        "ndcg": mean([n for _, _, n in rows]),
    }


CANDIDATES = [
    Candidate("gemini", "gemini-embedding-001", 768),
    Candidate("gemini", "gemini-embedding-001", 1536),
    Candidate("gemini", "gemini-embedding-2", 768),
    Candidate("openrouter", "openai/text-embedding-3-large", 1536),
    Candidate("openrouter", "openai/text-embedding-3-small", 1536),
]


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bake_off", description="Score embedding candidates against the §15 corpus (§18.1)."
    )
    parser.add_argument("--only", action="append", help="restrict to candidates matching a string")
    args = parser.parse_args(argv)

    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)
    assert container.engine is not None
    corpus = load_corpus_or_exit()

    chosen = [c for c in CANDIDATES if not args.only or any(frag in c.label for frag in args.only)]

    reports = []
    try:
        for candidate in chosen:
            try:
                reports.append(await score_candidate(candidate, settings, corpus))
                print(f"scored {candidate.label}", file=sys.stderr)
            except EmbeddingError as exc:
                print(f"{candidate.label}: {exc}", file=sys.stderr)
    finally:
        await container.engine.dispose()

    if not reports:
        return 1

    print(
        f"\n{'candidate':46} {'dims':>5} {'AR-rec':>7} {'AR-MRR':>7} "
        f"{'EN-rec':>7} {'EN-MRR':>7} {'nDCG':>6} {'q ms':>6} {'backfill':>9}"
    )
    print("-" * 108)
    for r in sorted(reports, key=lambda r: -r["by_language"].get("ar", {}).get("recall", 0)):
        ar = r["by_language"].get("ar", {"recall": 0, "mrr": 0})
        en = r["by_language"].get("en", {"recall": 0, "mrr": 0})
        print(
            f"{r['candidate'].label:46} {r['dimensions']:>5} "
            f"{ar['recall']:>7.2f} {ar['mrr']:>7.2f} {en['recall']:>7.2f} {en['mrr']:>7.2f} "
            f"{r['overall']['ndcg']:>6.2f} {r['query_ms']:>6.0f} {r['backfill_ms']:>8.0f}ms"
        )
    print(
        "\nsemantic leg only, inside each case's deterministic filters — not comparable to the "
        "phase-4 lexical baseline, only to each other."
    )
    for r in reports:
        if r["misses"]:
            print(f"\n{r['candidate'].label} missed: {', '.join(r['misses'])}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
