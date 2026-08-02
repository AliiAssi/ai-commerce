from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from tests.support.relevance_dto import RelevanceReportDTO


class IRelevanceService(ABC):
    @abstractmethod
    async def score(
        self,
        *,
        label: str,
        include_drafts: bool = True,
        only: Sequence[str] | None = None,
        enforce_cutoff: bool = False,
    ) -> RelevanceReportDTO: ...
