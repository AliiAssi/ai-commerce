from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.application.dtos.search_dto import (
    CatalogLexiconDTO,
    QueryVectorDTO,
    RetrievalRequest,
    RetrievalResult,
)
from app.application.rerank.ireranker import RerankCandidate


class ISearchRepository(ABC):
    @abstractmethod
    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...

    @abstractmethod
    async def rerank_candidates(self, product_ids: Sequence[int]) -> list[RerankCandidate]: ...

    @abstractmethod
    async def cached_query_vector(self, cache_key: str) -> QueryVectorDTO | None: ...

    @abstractmethod
    async def store_query_vector(
        self, cache_key: str, vector: QueryVectorDTO, *, language: str, ttl_seconds: int
    ) -> None: ...

    @abstractmethod
    async def catalog_terms(self) -> CatalogLexiconDTO: ...

    @abstractmethod
    async def detect_capabilities(self): ...
