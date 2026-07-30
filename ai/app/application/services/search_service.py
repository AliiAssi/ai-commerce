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
from app.application.rerank.ireranker import IReranker
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
    """Parse, embed, retrieve, rerank, and report honestly what happened.

    **It holds no session.** Every database touch opens its own short scope, because the
    embedding provider is called between two of them and §11 rule 9 forbids a transaction
    spanning a network call. That is not a theoretical rule here: the pool is five connections
    total, shared with the index worker, and a 434 ms p50 provider call held across one of them
    would take the store down under any concurrency at all. This is the same shape web's
    `ICatalogSearchService` took in phase 2, and for the same reason.

    The reporting half is not decoration. §9.2 requires the response to say which retrieval path
    actually ran, and §18's prohibitions include "silently ship lexical-only search under the
    name semantic search" — so a query whose semantic leg did not run is reported as `lexical`
    and `degraded`, with the reason code saying why.
    """

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
        # Defaulted for the same reason IndexService's is: the container resolves by exact type
        # annotation and a Callable alias never matches a binding.
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
            result = await scope.resolve(ISearchRepository).retrieve(
                RetrievalRequest(
                    semantic_text=intent.semantic_text,
                    normalized_query=intent.normalized_query,
                    filters=filters,
                    page=query.page,
                    page_size=query.page_size,
                    query_vector=query_vector,
                )
            )

        rerank = await self._reranker.rerank(
            intent, result.product_ids, window=self._settings.RERANKER_TOP_K
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

    # ---- the query embedding, and the cache that makes it affordable ---------------------------

    async def _query_vector(self, intent: SearchIntent) -> tuple[QueryVectorDTO | None, bool]:
        """One query embedding, cached, or nothing plus the reason it is nothing.

        Returns `(vector, embedding_failed)`. The flag distinguishes the two ways of having no
        vector that §9.2 reports differently: a configuration where the feature is simply off,
        and a provider that failed. Both degrade to the same retrieval; only one is a fault.

        Three scopes at most, and never one spanning the provider call:

          1. read the cache;
          2. *no transaction* — call the provider;
          3. write the cache.

        The write is its own scope rather than being folded into the retrieval scope below, so a
        cache insert that loses a race cannot abort the transaction the shopper's results are
        about to be read in.
        """
        if not self._settings.SMART_SEARCH_ENABLED or not intent.semantic_text:
            return None, False
        if not self._providers.any_configured:
            return None, False

        # The key names the model, so a cached row can only be found by the client that produced
        # it. The slot the vector belongs to is the primary's unless the primary is unusable.
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
            # A cache hit avoids the provider entirely (§14.1). The slot is restored here rather
            # than stored, because the key already pins the model that produced the row.
            return cached.model_copy(update={"slot": slot}), False

        try:
            batch, used_slot = await self._providers.embed_query(intent.semantic_text)
        except EmbeddingError as exc:
            # §12: never a 500 when lexical search can run. The code is logged, never returned.
            logger.warning("query embedding unavailable (%s); serving lexical results", exc.code)
            return None, True

        vector = QueryVectorDTO(
            values=batch.vectors[0],
            slot=used_slot,
            embedding_model=batch.model,
            dimensions=batch.dimensions,
        )
        # Only the primary's vectors are cached under this key. A fallback vector was produced by
        # a different model, so it belongs under a different key, and computing that key would
        # mean a second hash for a path that is already the unhappy one.
        if used_slot == slot:
            async with self._scope_factory() as scope:
                await scope.resolve(ISearchRepository).store_query_vector(
                    key,
                    vector,
                    language=intent.language,
                    ttl_seconds=self._settings.SEARCH_QUERY_CACHE_TTL_SECONDS,
                )
        return vector, False

    # ---- what to tell the client ---------------------------------------------------------------

    def _classify(
        self,
        intent: SearchIntent,
        result: RetrievalResult,
        *,
        embedding_failed: bool,
        reranked: bool,
    ) -> tuple[SearchMode, DegradedReason | None]:
        """Which mode ran, and whether that counts as degraded.

        Classification reads the *intent* and what retrieval reports having run, never what it
        happened to find. A query with semantic text that matched nothing and fell back to its
        filters is still a text search that underperformed — calling it `filters_only` would
        report a healthy mode for a degraded outcome. Equally, a semantic leg that ran and found
        nothing above the similarity floor is `hybrid` and not degraded: it answered, and the
        answer was "nothing here".
        """
        if not intent.normalized_query:
            return "browse", None
        if not intent.semantic_text:
            # Nothing to embed (§7.2), so this mode is never degraded — it is the complete and
            # correct answer to a pure constraint list.
            return "filters_only", None
        if not self._settings.SMART_SEARCH_ENABLED:
            return "lexical", "feature_disabled"
        if embedding_failed:
            return "lexical", "embedding_unavailable"
        if not result.semantic_used:
            # The provider answered, or was never asked, but the column is not populated enough
            # to read. §12 lists index coverage below the safe threshold as its own trigger, and
            # it is the honest reason: nothing failed, the index is not ready.
            return "lexical", "index_incomplete"
        # Phase 7 turns this into `hybrid_reranked`. A pass-through reranker is not a failure and
        # not degradation — `reranked: false` already says what happened, and reporting
        # `reranker_unavailable` would show every shopper a fault banner for a configuration
        # state (see PassthroughReranker).
        return ("hybrid_reranked" if reranked else "hybrid"), None
