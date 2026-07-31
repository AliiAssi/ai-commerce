from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.search_dto import SearchQuery, SearchResultDTO


class ISearchService(ABC):
    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResultDTO: ...
