from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.search_dto import CatalogLexiconDTO, RetrievalRequest, RetrievalResult


class ISearchRepository(ABC):
    """Candidate retrieval and fusion.

    Phase 1 implements the lexical and trigram legs. The semantic leg joins the same fusion in
    phase 6, which is why the return type already carries per-leg ranks: a caller must be able
    to tell which legs actually contributed without the repository reporting a mode of its own.
    """

    @abstractmethod
    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...

    @abstractmethod
    async def catalog_terms(self) -> CatalogLexiconDTO:
        """The live category slugs and distinct origins, for validating the alias file."""

    @abstractmethod
    async def detect_capabilities(self):
        """Which optional database features this database actually has."""
