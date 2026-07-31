from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.iservices.isearch_service import ISearchService
from app.core.auth import require_internal_key
from app.core.container import container
from app.presentation.schemas.search_schemas import SearchRequest, SearchResponse

router = APIRouter()


@router.post("/search", response_model=SearchResponse, dependencies=[Depends(require_internal_key)])
async def search(body: SearchRequest) -> SearchResponse:
    service = container.resolve(ISearchService)
    return SearchResponse.from_dto(await service.search(body.to_query()))
