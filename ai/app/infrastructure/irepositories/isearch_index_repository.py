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
    @abstractmethod
    async def drifted_product_ids(
        self, expectations: Sequence[VectorExpectationDTO] = ()
    ) -> list[int]: ...

    @abstractmethod
    async def enqueue_drifted(self, expectations: Sequence[VectorExpectationDTO] = ()) -> int: ...

    @abstractmethod
    async def enqueue_products(self, product_ids: Sequence[int], *, reset: bool) -> int: ...

    @abstractmethod
    async def active_product_ids(self) -> list[int]: ...

    @abstractmethod
    async def claim_batch(
        self, *, worker_id: str, size: int, lease_seconds: int, max_attempts: int
    ) -> list[ClaimedJobDTO]: ...

    @abstractmethod
    async def load_rows(self, product_ids: Sequence[int]) -> list[CatalogRowDTO]: ...

    @abstractmethod
    async def write_documents(
        self,
        documents: Sequence[SearchDocumentDTO],
        vectors: Mapping[str, EmbeddedSlot] | None = None,
    ) -> int: ...

    @abstractmethod
    async def complete(self, product_ids: Sequence[int]) -> int: ...

    @abstractmethod
    async def fail(
        self,
        product_id: int,
        *,
        error_code: str,
        delay_seconds: float,
        attempts: int | None = None,
    ) -> None: ...

    @abstractmethod
    async def release_leases(self, worker_id: str) -> int: ...

    @abstractmethod
    async def prune_documents(self) -> int: ...

    @abstractmethod
    async def coverage(
        self, expectations: Sequence[VectorExpectationDTO] = ()
    ) -> IndexCoverageDTO: ...

    @abstractmethod
    async def prune_query_cache(self) -> int: ...

    @abstractmethod
    async def pending_count(self) -> int: ...

    @abstractmethod
    async def failed_jobs(self, max_attempts: int) -> list[FailedJobDTO]: ...
