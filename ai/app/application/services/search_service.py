from __future__ import annotations

import logging

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
        intent = self._parser.parse(query.q)
        filters = resolve_filters(
            intent,
            self._aliases,
            explicit=query.explicit,
            ignore_inferred=query.ignore_inferred,
        )

        query_vector, embedding_failed = await self._query_vector(intent)

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

        rerank = await self._reranker.rerank(
            intent, candidates, window=self._settings.RERANKER_TOP_K
        )
        if len(candidates) != len(result.product_ids):
            rerank = RerankResult(
                result.product_ids, outcome=RERANK_SKIPPED, version=rerank.version
            )

        mode, degraded_reason = self._classify(
            intent, result, embedding_failed=embedding_failed, reranked=rerank.applied
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
            return cached.model_copy(update={"slot": slot}), False

        try:
            batch, used_slot = await self._providers.embed_query(intent.semantic_text)
        except EmbeddingError as exc:
            logger.warning("query embedding unavailable (%s); serving lexical results", exc.code)
            return None, True

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
