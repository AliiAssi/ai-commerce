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
    """The indexing pipeline, in units of work that hold no transaction between them.

    Both callers drive the same methods: the background worker in this service's lifespan, and
    the `reindex_catalog` CLI. §11 requires the claim protocol to support an out-of-process
    worker without redesign, and having one implementation with two drivers is what proves it.
    """

    @abstractmethod
    async def sweep(self) -> SweepReportDTO:
        """Prune, enqueue hash drift, and refresh the coverage gate (§0.4)."""

    @abstractmethod
    async def run_batch(self) -> IndexRunReportDTO:
        """Claim, build, and store one batch. Returns an empty report when nothing is due."""

    @abstractmethod
    async def drain(self, *, max_batches: int) -> IndexRunReportDTO:
        """Run batches until nothing more can be claimed."""

    @abstractmethod
    async def refresh_coverage(self) -> IndexCoverageDTO:
        """Re-measure coverage and settle whether retrieval may read the document table."""

    @abstractmethod
    async def enqueue(self, product_ids: Sequence[int], *, reset: bool) -> int:
        """Enqueue specific products; `reset` forces a retry of an exhausted job."""

    @abstractmethod
    async def enqueue_all_active(self, *, reset: bool) -> int:
        """Enqueue every non-archived product, for a full rebuild."""

    @abstractmethod
    async def drifted_product_ids(self) -> list[int]:
        """What a sweep would enqueue, without enqueuing it (`--dry-run`)."""

    @abstractmethod
    async def active_product_ids(self) -> list[int]:
        """Every non-archived product, for reporting what `--all` would touch."""

    @abstractmethod
    async def failed_jobs(self) -> list[FailedJobDTO]:
        """Jobs that exhausted their attempts."""

    @abstractmethod
    async def pending_count(self) -> int:
        """Jobs still queued, however they got there."""

    @abstractmethod
    async def release_leases(self) -> int:
        """Release this instance's leases on shutdown (§11 rule 7)."""

    @abstractmethod
    def backoff_seconds(self, attempts: int) -> float:
        """Capped exponential backoff for a job that has already failed `attempts` times."""
