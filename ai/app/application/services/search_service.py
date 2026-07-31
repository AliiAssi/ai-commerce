from __future__ import annotations

import logging
import time

from app.application.dtos.search_dto import (
    DegradedReason,
    QueryVectorDTO,
    RetrievalRequest,
    RetrievalResult,
    SearchIntent,
    SearchMode,
    SearchQuery,
    SearchResultDTO,
)
from app.application.iservices.isearch_service import ISearchService
from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.llm.iembedding_client import EmbeddingError
from app.application.rerank.ireranker import RERANK_SKIPPED, IReranker, RerankResult
from app.application.search.parser import IntentParser, resolve_filters
from app.application.search.query_cache import query_cache_key
from app.core.config import Settings
from app.core.container import ScopeFactory, open_scope
from app.core.index_state import IndexCoverage
from app.core.search_aliases import AliasLibrary
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.repositories.search_repository import RANKER_VERSION

logger = logging.getLogger(__name__)


class SearchService(ISearchService):
    def __init__(
        self,
        parser: IntentParser,
        aliases: AliasLibrary,
        providers: EmbeddingProviders,
        reranker: IReranker,
        coverage: IndexCoverage,
        settings: Settings,
        scope_factory: ScopeFactory = open_scope,
    ) -> None:
        self._parser = parser
        self._aliases = aliases
        self._providers = providers
        self._reranker = reranker
        self._coverage = coverage
        self._settings = settings
        self._scope_factory = scope_factory

    async def search(self, query: SearchQuery) -> SearchResultDTO:
        started = time.perf_counter()
        intent = self._parser.parse(query.q)
        filters = resolve_filters(
            intent,
            self._aliases,
            explicit=query.explicit,
            ignore_inferred=query.ignore_inferred,
        )
        logger.debug(
            "parse q=%r language=%s semantic=%r filters=%s sort=%s",
            intent.original_query,
            intent.language,
            intent.semantic_text,
            filters.model_dump(exclude={"inferred_filters", "ignored_inferred"}, exclude_none=True),
            filters.sort,
        )

        embed_started = time.perf_counter()
        query_vector, embedding_failed = await self._query_vector(intent)
        embed_ms = (time.perf_counter() - embed_started) * 1000

        retrieve_started = time.perf_counter()
        async with self._scope_factory() as scope:
            repository = scope.resolve(ISearchRepository)
            result = await repository.retrieve(
                RetrievalRequest(
                    semantic_text=intent.semantic_text,
                    normalized_query=intent.normalized_query,
                    filters=filters,
                    page=query.page,
                    page_size=query.page_size,
                    query_vector=query_vector,
                )
            )
            candidates = await repository.rerank_candidates(result.product_ids)
        retrieve_ms = (time.perf_counter() - retrieve_started) * 1000

        logger.info(
            "search retrieve q=%r legs sem=%d lex=%d trg=%d total=%d in %.0fms",
            intent.original_query,
            result.semantic_hits,
            result.lexical_hits,
            result.trigram_hits,
            result.total,
            retrieve_ms,
        )

        rerank_started = time.perf_counter()
        if filters.sort != "relevance":
            rerank = RerankResult(result.product_ids, outcome=RERANK_SKIPPED)
            logger.info("rerank skipped q=%r reason=explicit_sort(%s)", query.q, filters.sort)
        elif len(candidates) != len(result.product_ids):
            rerank = RerankResult(result.product_ids, outcome=RERANK_SKIPPED)
            logger.info(
                "rerank skipped q=%r reason=missing_documents (%d of %d have text)",
                query.q,
                len(candidates),
                len(result.product_ids),
            )
        else:
            before = list(result.product_ids)
            rerank = await self._reranker.rerank(
                intent, candidates, window=self._settings.RERANKER_TOP_K
            )
            rerank_ms = (time.perf_counter() - rerank_started) * 1000
            moved = sum(1 for a, b in zip(before, rerank.product_ids, strict=False) if a != b)
            logger.info(
                "rerank q=%r outcome=%s version=%s candidates=%d moved=%d in %.0fms",
                intent.original_query,
                rerank.outcome,
                rerank.version,
                len(candidates),
                moved,
                rerank_ms,
            )
            if moved:
                logger.debug("rerank order %s -> %s", before[:8], rerank.product_ids[:8])

        mode, degraded_reason = self._classify(
            intent, result, embedding_failed=embedding_failed, reranked=rerank.applied
        )
        logger.info(
            "search done q=%r mode=%s degraded=%s returned=%d "
            "timings embed=%.0fms retrieve=%.0fms total=%.0fms",
            intent.original_query,
            mode,
            degraded_reason or "no",
            len(rerank.product_ids),
            embed_ms,
            retrieve_ms,
            (time.perf_counter() - started) * 1000,
        )
        return SearchResultDTO(
            product_ids=rerank.product_ids,
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            query=intent.original_query,
            language=intent.language,
            mode=mode,
            reranked=rerank.applied,
            effective_sort=filters.sort,
            inferred_filters=filters.inferred_filters,
            ignored_inferred=list(filters.ignored_inferred),
            degraded=degraded_reason is not None,
            degraded_reason=degraded_reason,
            parser_version=intent.parser_version,
            lexicon_version=intent.lexicon_version,
            ranker_version=RANKER_VERSION,
        )

    async def _query_vector(self, intent: SearchIntent) -> tuple[QueryVectorDTO | None, bool]:
        if not self._settings.SMART_SEARCH_ENABLED or not intent.semantic_text:
            return None, False
        if not self._providers.any_configured:
            return None, False

        slot = self._providers.configured[0]
        model = self._providers.model(slot)
        dimensions = self._providers.dimensions(slot)
        if not model or not dimensions:
            return None, False

        key = query_cache_key(
            semantic_text=intent.semantic_text,
            language=intent.language,
            embedding_model=model,
            dimensions=dimensions,
        )
        async with self._scope_factory() as scope:
            cached = await scope.resolve(ISearchRepository).cached_query_vector(key)
        if cached is not None:
            logger.info(
                "embedding CACHE HIT q=%r model=%s dims=%d key=%s",
                intent.original_query,
                cached.embedding_model,
                cached.dimensions,
                key[:12],
            )
            return cached.model_copy(update={"slot": slot}), False

        call_started = time.perf_counter()
        try:
            batch, used_slot = await self._providers.embed_query(intent.semantic_text)
        except EmbeddingError as exc:
            logger.warning(
                "embedding FAILED q=%r code=%s retryable=%s in %.0fms; serving lexical results",
                intent.original_query,
                exc.code,
                exc.retryable,
                (time.perf_counter() - call_started) * 1000,
            )
            return None, True

        logger.info(
            "embedding CACHE MISS q=%r provider=%s model=%s dims=%d in %.0fms",
            intent.original_query,
            used_slot,
            batch.model,
            batch.dimensions,
            (time.perf_counter() - call_started) * 1000,
        )
        logger.debug(
            "embedding vector head=%s key=%s",
            [round(v, 4) for v in batch.vectors[0][:6]],
            key[:12],
        )

        vector = QueryVectorDTO(
            values=batch.vectors[0],
            slot=used_slot,
            embedding_model=batch.model,
            dimensions=batch.dimensions,
        )
        if used_slot == slot:
            async with self._scope_factory() as scope:
                await scope.resolve(ISearchRepository).store_query_vector(
                    key,
                    vector,
                    language=intent.language,
                    ttl_seconds=self._settings.SEARCH_QUERY_CACHE_TTL_SECONDS,
                )
        return vector, False

    def _classify(
        self,
        intent: SearchIntent,
        result: RetrievalResult,
        *,
        embedding_failed: bool,
        reranked: bool,
    ) -> tuple[SearchMode, DegradedReason | None]:
        if not intent.normalized_query:
            return "browse", None
        if not intent.semantic_text:
            return "filters_only", None
        if not self._settings.SMART_SEARCH_ENABLED:
            return "lexical", "feature_disabled"
        if embedding_failed:
            return "lexical", "embedding_unavailable"
        if not result.semantic_used:
            return "lexical", "index_incomplete"
        return ("hybrid_reranked" if reranked else "hybrid"), None
