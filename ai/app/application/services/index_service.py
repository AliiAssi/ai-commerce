from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.application.dtos.index_dto import (
    ERROR_DATABASE,
    ERROR_UNEXPECTED,
    CatalogRowDTO,
    ClaimedJobDTO,
    EmbeddedSlot,
    FailedJobDTO,
    IndexCoverageDTO,
    IndexRunReportDTO,
    SearchDocumentDTO,
    SweepReportDTO,
    VectorExpectationDTO,
    embedding_error_code,
)
from app.application.iservices.iindex_service import IIndexService
from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.llm.iembedding_client import EmbeddingError
from app.application.search.document import build_document
from app.core.config import Settings
from app.core.container import ScopeFactory, open_scope
from app.core.index_state import IndexCoverage
from app.infrastructure.irepositories.isearch_index_repository import ISearchIndexRepository

logger = logging.getLogger(__name__)


class IndexService(IIndexService):
    def __init__(
        self,
        settings: Settings,
        coverage: IndexCoverage,
        providers: EmbeddingProviders,
        scope_factory: ScopeFactory = open_scope,
    ) -> None:
        self._settings = settings
        self._coverage = coverage
        self._providers = providers
        self._scope_factory = scope_factory
        self._last_cache_prune = 0.0
        self.worker_id = f"{uuid4().hex[:16]}:{os.getpid()}"

    def _expectations(self) -> list[VectorExpectationDTO]:
        expectations = []
        for slot in self._providers.configured:
            model = self._providers.model(slot)
            dimensions = self._providers.dimensions(slot)
            if model and dimensions:
                expectations.append(
                    VectorExpectationDTO(
                        slot=slot, embedding_model=model, embedding_dimensions=dimensions
                    )
                )
        return expectations

    async def sweep(self) -> SweepReportDTO:
        expectations = self._expectations()
        async with self._scope_factory() as scope:
            pruned = await scope.resolve(ISearchIndexRepository).prune_documents()
        async with self._scope_factory() as scope:
            enqueued = await scope.resolve(ISearchIndexRepository).enqueue_drifted(expectations)
        coverage = await self.refresh_coverage()
        await self.prune_query_cache()

        if pruned or enqueued:
            logger.info(
                "index sweep: %d pruned, %d enqueued, coverage %d/%d",
                pruned,
                enqueued,
                coverage.documents,
                coverage.active_products,
            )
        return SweepReportDTO(pruned=pruned, enqueued=enqueued, coverage=coverage)

    async def refresh_coverage(self) -> IndexCoverageDTO:
        async with self._scope_factory() as scope:
            coverage = await scope.resolve(ISearchIndexRepository).coverage(self._expectations())
        was_ready = self._coverage.ready
        self._coverage.update(
            active_products=coverage.active_products,
            documents=coverage.documents,
            threshold=self._settings.SEARCH_INDEX_MIN_COVERAGE,
            embedded=coverage.embedded,
        )
        if self._coverage.ready != was_ready:
            logger.info(
                "search document index is now %s (%d/%d active products covered)",
                "in use" if self._coverage.ready else "not in use",
                coverage.documents,
                coverage.active_products,
            )
        return coverage

    async def run_batch(self) -> IndexRunReportDTO:
        claimed = await self._claim()
        if not claimed:
            return IndexRunReportDTO()

        product_ids = [job.product_id for job in claimed]
        try:
            async with self._scope_factory() as scope:
                rows = await scope.resolve(ISearchIndexRepository).load_rows(product_ids)

            documents = [build_document(row) for row in rows]

            vectors, embedding_error = await self._embed(rows, documents)

            writable = self._writable(rows, documents, failed=embedding_error is not None)

            async with self._scope_factory() as scope:
                repository = scope.resolve(ISearchIndexRepository)
                await repository.write_documents(writable, vectors)
                if embedding_error is None:
                    await repository.complete(product_ids)
        except SQLAlchemyError as exc:
            logger.warning("index batch failed: %s", exc.__class__.__name__)
            await self._fail(claimed, ERROR_DATABASE)
            return IndexRunReportDTO(claimed=len(claimed), failed=len(claimed))
        except Exception:
            logger.exception("index batch failed unexpectedly")
            await self._fail(claimed, ERROR_UNEXPECTED)
            return IndexRunReportDTO(claimed=len(claimed), failed=len(claimed))

        embedded = {slot: len(slot_vectors.vectors) for slot, slot_vectors in vectors.items()}
        if embedding_error is not None:
            await self._fail(
                claimed,
                embedding_error_code(embedding_error.code),
                permanent=not embedding_error.retryable,
            )
            return IndexRunReportDTO(
                claimed=len(claimed),
                indexed=len(writable),
                failed=len(claimed),
                embedded=embedded,
            )
        return IndexRunReportDTO(claimed=len(claimed), indexed=len(documents), embedded=embedded)

    async def _embed(
        self, rows: Sequence[CatalogRowDTO], documents: Sequence[SearchDocumentDTO]
    ) -> tuple[dict[str, EmbeddedSlot], EmbeddingError | None]:
        vectors: dict[str, EmbeddedSlot] = {}
        by_id = {row.product_id: row for row in rows}

        for slot in self._providers.configured:
            model = self._providers.model(slot)
            dimensions = self._providers.dimensions(slot)
            stale = [
                document
                for document in documents
                if not by_id[document.product_id].vector(slot).matches(model, dimensions)
                or by_id[document.product_id].stored_hash != document.document_hash
            ]
            if not stale:
                continue
            try:
                batch = await self._providers.embed_documents(
                    slot, [document.document_text for document in stale]
                )
            except EmbeddingError as exc:
                logger.warning("embedding slot %s failed: %s", slot, exc.code)
                return vectors, exc
            if batch is None:
                continue
            vectors[slot] = EmbeddedSlot(
                model=batch.model,
                dimensions=batch.dimensions,
                vectors={
                    document.product_id: vector
                    for document, vector in zip(stale, batch.vectors, strict=True)
                },
            )
        return vectors, None

    @staticmethod
    def _writable(
        rows: Sequence[CatalogRowDTO],
        documents: Sequence[SearchDocumentDTO],
        *,
        failed: bool,
    ) -> list[SearchDocumentDTO]:
        if not failed:
            return list(documents)
        unindexed = {row.product_id for row in rows if not row.is_indexed}
        return [document for document in documents if document.product_id in unindexed]

    async def drain(self, *, max_batches: int) -> IndexRunReportDTO:
        claimed = indexed = failed = 0
        for _ in range(max_batches):
            report = await self.run_batch()
            if not report.claimed:
                break
            claimed += report.claimed
            indexed += report.indexed
            failed += report.failed
        return IndexRunReportDTO(claimed=claimed, indexed=indexed, failed=failed)

    async def _claim(self) -> list[ClaimedJobDTO]:
        async with self._scope_factory() as scope:
            return await scope.resolve(ISearchIndexRepository).claim_batch(
                worker_id=self.worker_id,
                size=self._settings.SEARCH_INDEX_BATCH_SIZE,
                lease_seconds=self._settings.SEARCH_INDEX_LEASE_SECONDS,
                max_attempts=self._settings.SEARCH_INDEX_MAX_ATTEMPTS,
            )

    async def _fail(
        self, claimed: Sequence[ClaimedJobDTO], error_code: str, *, permanent: bool = False
    ) -> None:
        max_attempts = self._settings.SEARCH_INDEX_MAX_ATTEMPTS
        try:
            async with self._scope_factory() as scope:
                repository = scope.resolve(ISearchIndexRepository)
                for job in claimed:
                    await repository.fail(
                        job.product_id,
                        error_code=error_code,
                        delay_seconds=self.backoff_seconds(job.attempts),
                        attempts=max_attempts if permanent else None,
                    )
        except SQLAlchemyError:
            logger.warning("could not record index failures; leases will expire instead")

    async def prune_query_cache(self) -> int:
        now = time.monotonic()
        if now - self._last_cache_prune < self._settings.SEARCH_QUERY_CACHE_PRUNE_SECONDS:
            return 0
        self._last_cache_prune = now
        async with self._scope_factory() as scope:
            pruned = await scope.resolve(ISearchIndexRepository).prune_query_cache()
        if pruned:
            logger.info("pruned %d expired query-embedding cache rows", pruned)
        return pruned

    def backoff_seconds(self, attempts: int) -> float:
        base = self._settings.SEARCH_INDEX_POLL_SECONDS
        cap = self._settings.SEARCH_INDEX_BACKOFF_CAP_SECONDS
        return min(base * (2 ** max(attempts, 0)), cap)

    async def enqueue(self, product_ids: Sequence[int], *, reset: bool) -> int:
        async with self._scope_factory() as scope:
            return await scope.resolve(ISearchIndexRepository).enqueue_products(
                product_ids, reset=reset
            )

    async def enqueue_all_active(self, *, reset: bool) -> int:
        async with self._scope_factory() as scope:
            repository = scope.resolve(ISearchIndexRepository)
            return await repository.enqueue_products(
                await repository.active_product_ids(), reset=reset
            )

    async def drifted_product_ids(self) -> list[int]:
        async with self._scope_factory() as scope:
            return await scope.resolve(ISearchIndexRepository).drifted_product_ids(
                self._expectations()
            )

    async def active_product_ids(self) -> list[int]:
        async with self._scope_factory() as scope:
            return await scope.resolve(ISearchIndexRepository).active_product_ids()

    async def failed_jobs(self) -> list[FailedJobDTO]:
        async with self._scope_factory() as scope:
            return await scope.resolve(ISearchIndexRepository).failed_jobs(
                self._settings.SEARCH_INDEX_MAX_ATTEMPTS
            )

    async def pending_count(self) -> int:
        async with self._scope_factory() as scope:
            return await scope.resolve(ISearchIndexRepository).pending_count()

    async def release_leases(self) -> int:
        async with self._scope_factory() as scope:
            return await scope.resolve(ISearchIndexRepository).release_leases(self.worker_id)
