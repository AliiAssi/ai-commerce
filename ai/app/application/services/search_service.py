from __future__ import annotations

import logging

from app.application.dtos.search_dto import (
    DegradedReason,
    RetrievalRequest,
    SearchMode,
    SearchQuery,
    SearchResultDTO,
)
from app.application.iservices.isearch_service import ISearchService
from app.application.search.parser import IntentParser, resolve_filters
from app.core.config import Settings
from app.core.search_aliases import AliasLibrary
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.repositories.search_repository import RANKER_VERSION

logger = logging.getLogger(__name__)


class SearchService(ISearchService):
    """Parse, reduce to filters, retrieve, and report honestly what happened.

    The reporting half is not decoration. §9.2 requires the response to say which retrieval
    path actually ran, and §18's prohibitions include "silently ship lexical-only search under
    the name semantic search" — so while the semantic leg does not exist, every text query is
    reported as `lexical` and `degraded`, with the reason code saying why.
    """

    def __init__(
        self,
        parser: IntentParser,
        aliases: AliasLibrary,
        repository: ISearchRepository,
        settings: Settings,
    ) -> None:
        self._parser = parser
        self._aliases = aliases
        self._repository = repository
        self._settings = settings

    async def search(self, query: SearchQuery) -> SearchResultDTO:
        intent = self._parser.parse(query.q)
        filters = resolve_filters(
            intent,
            self._aliases,
            explicit=query.explicit,
            ignore_inferred=query.ignore_inferred,
        )

        result = await self._repository.retrieve(
            RetrievalRequest(
                semantic_text=intent.semantic_text,
                normalized_query=intent.normalized_query,
                filters=filters,
                page=query.page,
                page_size=query.page_size,
            )
        )

        mode, degraded_reason = self._classify(intent.normalized_query, intent.semantic_text)
        return SearchResultDTO(
            product_ids=result.product_ids,
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            query=intent.original_query,
            language=intent.language,
            mode=mode,
            reranked=False,
            effective_sort=filters.sort,
            inferred_filters=filters.inferred_filters,
            ignored_inferred=list(filters.ignored_inferred),
            degraded=degraded_reason is not None,
            degraded_reason=degraded_reason,
            parser_version=intent.parser_version,
            lexicon_version=intent.lexicon_version,
            ranker_version=RANKER_VERSION,
        )

    def _classify(
        self, normalized_query: str, semantic_text: str
    ) -> tuple[SearchMode, DegradedReason | None]:
        """Which mode ran, and whether that counts as degraded.

        Classification reads the *intent*, not what retrieval happened to find. A query with
        semantic text that matched nothing and fell back to its filters is still a text search
        that underperformed — calling it `filters_only` would report a healthy mode for a
        degraded outcome.
        """
        if not normalized_query:
            return "browse", None
        if not semantic_text:
            # Nothing to embed even once embeddings exist (§7.2), so this mode is never
            # degraded — it is the complete and correct answer to a pure constraint list.
            return "filters_only", None
        # Phases 6 and 7 are what turn this into `hybrid` and `hybrid_reranked`.
        if not self._settings.SMART_SEARCH_ENABLED:
            return "lexical", "feature_disabled"
        return "lexical", "index_incomplete"
