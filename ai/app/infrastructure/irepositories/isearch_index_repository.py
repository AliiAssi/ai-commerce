from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from app.application.dtos.index_dto import (
    CatalogRowDTO,
    ClaimedJobDTO,
    EmbeddedSlot,
    FailedJobDTO,
    IndexCoverageDTO,
    SearchDocumentDTO,
    VectorExpectationDTO,
)


class ISearchIndexRepository(ABC):
    """Every statement the indexing pipeline issues.

    Each method is one short unit of work. Nothing here opens or holds a transaction across
    more than its own statement, because §11 rule 9 forbids a transaction spanning the provider
    call that phase 6 adds between the load and the write.
    """

    # ---- enqueue ---------------------------------------------------------------------------

    @abstractmethod
    async def drifted_product_ids(
        self, expectations: Sequence[VectorExpectationDTO] = ()
    ) -> list[int]:
        """Active products whose stored document disagrees with live catalog data (§0.4).

        `expectations` adds the vector conditions: a document whose text is current but whose
        vector is missing or was produced by a different model is drifted too, and no hash
        comparison can see that. Empty means text conditions only.
        """

    @abstractmethod
    async def enqueue_drifted(self, expectations: Sequence[VectorExpectationDTO] = ()) -> int:
        """Enqueue the drifted set, coalescing on product_id. Returns rows actually inserted."""

    @abstractmethod
    async def enqueue_products(self, product_ids: Sequence[int], *, reset: bool) -> int:
        """Enqueue specific products. `reset` clears attempts, for an operator-forced retry."""

    @abstractmethod
    async def active_product_ids(self) -> list[int]:
        """Every non-archived product, for a full rebuild."""

    # ---- claim and finish ------------------------------------------------------------------

    @abstractmethod
    async def claim_batch(
        self, *, worker_id: str, size: int, lease_seconds: int, max_attempts: int
    ) -> list[ClaimedJobDTO]:
        """Lease a batch of due jobs with FOR UPDATE SKIP LOCKED (§11 rule 1)."""

    @abstractmethod
    async def load_rows(self, product_ids: Sequence[int]) -> list[CatalogRowDTO]:
        """Live semantic fields for the claimed products, archived ones excluded.

        Each row also carries what the index currently holds for it, so the caller can embed only
        the halves that are actually stale rather than paying for the whole document again.
        """

    @abstractmethod
    async def write_documents(
        self,
        documents: Sequence[SearchDocumentDTO],
        vectors: Mapping[str, EmbeddedSlot] | None = None,
    ) -> int:
        """Upsert documents, their weighted tsvectors, and whichever vectors were produced.

        A slot with no vector for a product leaves that column exactly as it was: §11 forbids
        discarding the last known-good index before a replacement is stored.
        """

    @abstractmethod
    async def complete(self, product_ids: Sequence[int]) -> int:
        """Remove finished jobs."""

    @abstractmethod
    async def fail(
        self,
        product_id: int,
        *,
        error_code: str,
        delay_seconds: float,
        attempts: int | None = None,
    ) -> None:
        """Record an attempt, back the job off, and release its lease.

        `attempts` forces the count, so a permanent provider error reaches the cap immediately
        rather than retrying its way there (§11 rule 6).
        """

    @abstractmethod
    async def release_leases(self, worker_id: str) -> int:
        """Hand back this worker's leases so a redeploy does not wait them out (§11 rule 7)."""

    # ---- repair and reporting --------------------------------------------------------------

    @abstractmethod
    async def prune_documents(self) -> int:
        """Delete documents whose product is archived or gone."""

    @abstractmethod
    async def coverage(self, expectations: Sequence[VectorExpectationDTO] = ()) -> IndexCoverageDTO:
        """Active products, how many have a document, and how many have a current vector per slot.

        One statement, so document readiness and vector readiness describe the same instant.
        """

    @abstractmethod
    async def prune_query_cache(self) -> int:
        """Delete expired query-embedding cache rows (§10.4)."""

    @abstractmethod
    async def pending_count(self) -> int:
        """Jobs still in the queue, whether due, backed off, or exhausted."""

    @abstractmethod
    async def failed_jobs(self, max_attempts: int) -> list[FailedJobDTO]:
        """Jobs that ran out of attempts and need an operator (§11 rule 6)."""
