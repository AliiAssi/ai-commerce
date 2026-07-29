from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.relevance_dto import RelevanceReportDTO


class IRelevanceService(ABC):
    """Runs the §15 corpus against live retrieval and scores it.

    Used by the `score_relevance` CLI and by the integration suite, so the number quoted in a
    phase gate is produced by the same code that guards it in CI.
    """

    @abstractmethod
    async def score(self, *, label: str, include_drafts: bool = True) -> RelevanceReportDTO:
        """Run every case and compute §15's gates, per language and overall."""
