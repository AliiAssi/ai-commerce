from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.search_dto import (
    CatalogLexiconDTO,
    QueryVectorDTO,
    RetrievalRequest,
    RetrievalResult,
)


class ISearchRepository(ABC):
    """Candidate retrieval and fusion.

    The return type carries per-leg ranks so a caller can tell which legs actually contributed
    without the repository reporting a mode of its own — §9.2's mode is a statement about the
    whole request, and retrieval only knows its own part of it.
    """

    @abstractmethod
    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...

    @abstractmethod
    async def cached_query_vector(self, cache_key: str) -> QueryVectorDTO | None:
        """A live query embedding for this key, or None when absent or expired (§10.4)."""

    @abstractmethod
    async def store_query_vector(
        self, cache_key: str, vector: QueryVectorDTO, *, language: str, ttl_seconds: int
    ) -> None:
        """Cache one query embedding. Idempotent: a concurrent duplicate must not raise."""

    @abstractmethod
    async def catalog_terms(self) -> CatalogLexiconDTO:
        """The live category slugs and distinct origins, for validating the alias file."""

    @abstractmethod
    async def detect_capabilities(self):
        """Which optional database features this database actually has."""
