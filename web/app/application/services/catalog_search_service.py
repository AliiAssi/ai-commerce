from __future__ import annotations

import logging

from app.application.dtos.product_dto import (
    ProductListDTO,
    ProductSearchParams,
    SearchMetadataDTO,
)
from app.application.iservices.iai_gateway import IAIGateway
from app.application.iservices.icatalog_search_service import ICatalogSearchService
from app.core.config import Settings
from app.core.container import ScopeFactory
from app.infrastructure.irepositories.iproduct_repository import IProductRepository

logger = logging.getLogger(__name__)


class CatalogSearchService(ICatalogSearchService):
    """Routes public catalog search to the AI service, and serves lexical when it cannot.

    The fallback is the deliverable here, not the happy path. §12 requires search to degrade
    rather than fail, and this is the only place in the storefront where that degradation is
    decided — so it must be true that *every* way the AI service can let us down ends up on the
    same lexical path, without a 500 and without a provider detail reaching the shopper.

    This service holds no database session. It takes a ScopeFactory and opens short scopes
    around its own queries, because §8.2 forbids a transaction or a checked-out connection
    being held across a call to another service — and web's ordinary request scope opens a
    transaction for the whole request.
    """

    def __init__(self, scopes: ScopeFactory, gateway: IAIGateway, settings: Settings) -> None:
        self._scopes = scopes
        self._gateway = gateway
        self._settings = settings

    async def search(self, params: ProductSearchParams) -> ProductListDTO:
        if not self._routes_to_ai(params):
            return await self._lexical(params, degraded_reason=None)

        # No scope is open across this call — that is the entire point of the split.
        result = await self._gateway.search(params)
        if result is None:
            # Routing was on and the service could not answer: unreachable, slow, erroring, or
            # incoherent. All four are one outage as far as the shopper is concerned, and one
            # reason code as far as §13's analytics are concerned — distinct from the store
            # being configured to serve its own search.
            return await self._lexical(params, degraded_reason="search_unavailable")

        async with self._scopes.open() as scope:
            products = await scope.resolve(IProductRepository).list_by_ids(result.product_ids)

        return ProductListDTO(
            items=products,
            # The AI service counted the matched set; hydration only drops rows archived in
            # the moment between the two queries, which must not silently change the total's
            # meaning. Pagination stays consistent with what retrieval actually matched.
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            search=SearchMetadataDTO(
                query=result.query,
                language=result.language,
                mode=result.mode,
                reranked=result.reranked,
                effective_sort=result.effective_sort,
                inferred_filters=result.inferred_filters,
                ignored_inferred=result.ignored_inferred,
                degraded=result.degraded,
                degraded_reason=result.degraded_reason,
            ),
        )

    def _routes_to_ai(self, params: ProductSearchParams) -> bool:
        # An empty query is ordinary browsing (§5.1) and never leaves this service. That also
        # keeps the storefront's front page working when the AI service is asleep.
        if not (params.q or "").strip():
            return False
        return bool(self._settings.SMART_SEARCH_ROUTING_ENABLED and self._settings.AI_SERVICE_URL)

    async def _lexical(
        self, params: ProductSearchParams, *, degraded_reason: str | None
    ) -> ProductListDTO:
        """The existing full-text search, reported honestly as what it is."""
        async with self._scopes.open() as scope:
            page = await scope.resolve(IProductRepository).search(params)

        query = (params.q or "").strip()
        if not query:
            # Browsing. §9.2 still wants a `search` object so clients can read the effective
            # sort without inferring it, but nothing here is degraded.
            page.search = SearchMetadataDTO(
                query="",
                language="en",
                mode="browse",
                effective_sort=params.effective_sort,
            )
            return page

        page.search = SearchMetadataDTO(
            query=query,
            # Web does no language detection of its own — that lives in the AI service's
            # normalizer, and guessing here would contradict it. The field stays honest by
            # reporting the catalog's language rather than a guess about the query's.
            language="en",
            mode="lexical",
            effective_sort=params.effective_sort,
            degraded=degraded_reason is not None,
            degraded_reason=degraded_reason,
        )
        return page
