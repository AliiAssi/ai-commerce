from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.iservices.isearch_service import ISearchService
from app.core.auth import require_internal_key
from app.core.container import container
from app.presentation.schemas.search_schemas import SearchRequest, SearchResponse

router = APIRouter()


# POST rather than GET, for the same reason the chat endpoint is a POST: this is a
# service-to-service call, never a shareable URL, and a body keeps a 200-character bilingual
# query and a repeatable ignore_inferred list out of a query string and out of access logs.
# The shopper's shareable URL is web's /api/v1/products, which stays a GET.
#
# Resolved from the container directly rather than through `Injected(...)`, which is not a style
# choice. `Injected` opens a scope — and `open_scope` begins a transaction — before the handler
# body runs, so the whole request would hold one of five pooled connections across the embedding
# provider call inside it (§11 rule 9, §8.2). The service opens its own short scopes instead, the
# same arrangement web's search gateway uses, and a test asserts no connection is checked out
# while the provider is being called.
@router.post("/search", response_model=SearchResponse, dependencies=[Depends(require_internal_key)])
async def search(body: SearchRequest) -> SearchResponse:
    service = container.resolve(ISearchService)
    return SearchResponse.from_dto(await service.search(body.to_query()))
