from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.relevance_dto import RelevanceReportDTO


class IRelevanceService(ABC):
    @abstractmethod
    async def score(self, *, label: str, include_drafts: bool = True) -> RelevanceReportDTO: ...
