from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.application.dtos.index_dto import (
    FailedJobDTO,
    IndexCoverageDTO,
    IndexRunReportDTO,
    SweepReportDTO,
)


class IIndexService(ABC):
    @abstractmethod
    async def sweep(self) -> SweepReportDTO: ...

    @abstractmethod
    async def run_batch(self) -> IndexRunReportDTO: ...

    @abstractmethod
    async def drain(self, *, max_batches: int) -> IndexRunReportDTO: ...

    @abstractmethod
    async def refresh_coverage(self) -> IndexCoverageDTO: ...

    @abstractmethod
    async def enqueue(self, product_ids: Sequence[int], *, reset: bool) -> int: ...

    @abstractmethod
    async def enqueue_all_active(self, *, reset: bool) -> int: ...

    @abstractmethod
    async def drifted_product_ids(self) -> list[int]: ...

    @abstractmethod
    async def active_product_ids(self) -> list[int]: ...

    @abstractmethod
    async def failed_jobs(self) -> list[FailedJobDTO]: ...

    @abstractmethod
    async def pending_count(self) -> int: ...

    @abstractmethod
    async def release_leases(self) -> int: ...

    @abstractmethod
    async def prune_query_cache(self) -> int: ...

    @abstractmethod
    def backoff_seconds(self, attempts: int) -> float: ...
