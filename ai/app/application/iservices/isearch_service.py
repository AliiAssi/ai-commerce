from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.search_dto import SearchQuery, SearchResultDTO


class ISearchService(ABC):
    """The canonical smart-search pipeline.

    One implementation serves all three surfaces. The storefront reaches it over HTTP through
    web's gateway; chat and MCP call it in-process from phase 8. That is the point of the
    ownership decision in the plan's §0 — there is no second pipeline to keep in step.
    """

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResultDTO: ...
