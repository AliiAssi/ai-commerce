from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.application.dtos.index_dto import (
    ERROR_DATABASE,
    ERROR_UNEXPECTED,
    ClaimedJobDTO,
    FailedJobDTO,
    IndexCoverageDTO,
    IndexRunReportDTO,
    SweepReportDTO,
)
from app.application.iservices.iindex_service import IIndexService
from app.application.search.document import build_document
from app.core.config import Settings
from app.core.container import ScopeFactory, open_scope
from app.core.index_state import IndexCoverage
from app.infrastructure.irepositories.isearch_index_repository import ISearchIndexRepository

logger = logging.getLogger(__name__)


class IndexService(IIndexService):
    """Keeps `ai_search_documents` agreeing with the catalog the web service owns.

    It holds no session. Every step opens its own short scope and closes it, which is not
    tidiness: §11 rule 9 forbids a transaction spanning a provider call, and phase 6 adds the
    embedding call to `run_batch` in the gap this shape already leaves between loading the
    catalog rows and writing the documents. Building that gap now means phase 6 changes what
    happens inside the loop rather than how the loop is written.

    `scope_factory` carries a default because the container resolves constructor parameters by
    exact type annotation and a Callable alias never matches a binding — the same reason
    `ToolRegistry` takes one this way.
    """

    def __init__(
        self,
        settings: Settings,
        coverage: IndexCoverage,
        scope_factory: ScopeFactory = open_scope,
    ) -> None:
        self._settings = settings
        self._coverage = coverage
        self._scope_factory = scope_factory
        # Identifies leases in the jobs table, so an operator can see which process is holding
        # what. Fits String(64) with room to spare.
        self.worker_id = f"{uuid4().hex[:16]}:{os.getpid()}"

    # ---- the sweep -------------------------------------------------------------------------

    async def sweep(self) -> SweepReportDTO:
        """§0.4's hash-drift sweep, which replaces §10.3's impossible transactional enqueue.

        Pruning runs first so a product archived since the last sweep stops counting against
        coverage in the same pass that measures it, rather than a sweep later.
        """
        async with self._scope_factory() as scope:
            pruned = await scope.resolve(ISearchIndexRepository).prune_documents()
        async with self._scope_factory() as scope:
            enqueued = await scope.resolve(ISearchIndexRepository).enqueue_drifted()
        coverage = await self.refresh_coverage()

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
            coverage = await scope.resolve(ISearchIndexRepository).coverage()
        was_ready = self._coverage.ready
        self._coverage.update(
            active_products=coverage.active_products,
            documents=coverage.documents,
            threshold=self._settings.SEARCH_INDEX_MIN_COVERAGE,
        )
        if self._coverage.ready != was_ready:
            # Worth a line at INFO either way: it is the difference between §12's step 3 and
            # step 4, and therefore between two different sets of search results.
            logger.info(
                "search document index is now %s (%d/%d active products covered)",
                "in use" if self._coverage.ready else "not in use",
                coverage.documents,
                coverage.active_products,
            )
        return coverage

    # ---- one batch -------------------------------------------------------------------------

    async def run_batch(self) -> IndexRunReportDTO:
        claimed = await self._claim()
        if not claimed:
            return IndexRunReportDTO()

        product_ids = [job.product_id for job in claimed]
        try:
            # A separate scope, so the lease is committed and no connection is held while the
            # documents are built. Phase 6's batch embedding call belongs between this scope
            # and the next one.
            async with self._scope_factory() as scope:
                rows = await scope.resolve(ISearchIndexRepository).load_rows(product_ids)

            documents = [build_document(row) for row in rows]

            async with self._scope_factory() as scope:
                repository = scope.resolve(ISearchIndexRepository)
                await repository.write_documents(documents)
                # Every claimed id is finished, including any that loaded nothing because the
                # product was archived between the sweep and now: the correct index state for
                # an archived product is no document, which the prune already produces, so
                # failing those would burn attempts on a normal condition.
                await repository.complete(product_ids)
        except SQLAlchemyError as exc:
            logger.warning("index batch failed: %s", exc.__class__.__name__)
            await self._fail(claimed, ERROR_DATABASE)
            return IndexRunReportDTO(claimed=len(claimed), failed=len(claimed))
        except Exception:
            logger.exception("index batch failed unexpectedly")
            await self._fail(claimed, ERROR_UNEXPECTED)
            return IndexRunReportDTO(claimed=len(claimed), failed=len(claimed))

        return IndexRunReportDTO(claimed=len(claimed), indexed=len(documents))

    async def drain(self, *, max_batches: int) -> IndexRunReportDTO:
        """Batches until the queue has nothing claimable left.

        `max_batches` is a guard, not a policy: a job that keeps failing backs off rather than
        staying claimable, so this terminates on its own, but a bug that made `complete` a no-op
        would otherwise spin forever inside a CLI run.
        """
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

    async def _fail(self, claimed: Sequence[ClaimedJobDTO], error_code: str) -> None:
        """Record the attempt against every job in the batch, in a scope of its own.

        It has to be a new scope: the failure that brought us here has already aborted the one
        that was open, and Postgres will run nothing else on that session.
        """
        try:
            async with self._scope_factory() as scope:
                repository = scope.resolve(ISearchIndexRepository)
                for job in claimed:
                    await repository.fail(
                        job.product_id,
                        error_code=error_code,
                        delay_seconds=self.backoff_seconds(job.attempts),
                    )
        except SQLAlchemyError:
            # The lease expires on its own, so the jobs come back regardless. Losing the error
            # code is not worth taking the worker down for.
            logger.warning("could not record index failures; leases will expire instead")

    def backoff_seconds(self, attempts: int) -> float:
        """Capped exponential backoff (§11 rule 5).

        `attempts` is the count before this failure, so the first retry waits one poll interval
        rather than two. The cap is what keeps a permanently broken product from pushing its
        next attempt years out before the attempt cap has been reached.
        """
        base = self._settings.SEARCH_INDEX_POLL_SECONDS
        cap = self._settings.SEARCH_INDEX_BACKOFF_CAP_SECONDS
        return min(base * (2 ** max(attempts, 0)), cap)

    # ---- enqueue and reporting ---------------------------------------------------------------

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
            return await scope.resolve(ISearchIndexRepository).drifted_product_ids()

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
