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
        providers: EmbeddingProviders,
        scope_factory: ScopeFactory = open_scope,
    ) -> None:
        self._settings = settings
        self._coverage = coverage
        self._providers = providers
        self._scope_factory = scope_factory
        self._last_cache_prune = 0.0
        # Identifies leases in the jobs table, so an operator can see which process is holding
        # what. Fits String(64) with room to spare.
        self.worker_id = f"{uuid4().hex[:16]}:{os.getpid()}"

    # ---- the sweep -------------------------------------------------------------------------

    def _expectations(self) -> list[VectorExpectationDTO]:
        """What each configured slot's stored vectors must agree with to count as current.

        Derived from the bound clients rather than from settings, so a slot with no provider
        contributes no condition at all. That is what keeps an unconfigured fallback column from
        being enqueued for backfill on every sweep and failing every time.

        Deliberately not gated on SMART_SEARCH_ENABLED. The flag governs whether *search* reads
        the vectors; whether the index carries them is a question about the index. Keeping them
        current while the flag is off is what makes turning it on instant instead of a cold
        start (§19).
        """
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
        """§0.4's hash-drift sweep, which replaces §10.3's impossible transactional enqueue.

        Pruning runs first so a product archived since the last sweep stops counting against
        coverage in the same pass that measures it, rather than a sweep later.
        """
        expectations = self._expectations()
        async with self._scope_factory() as scope:
            pruned = await scope.resolve(ISearchIndexRepository).prune_documents()
        async with self._scope_factory() as scope:
            enqueued = await scope.resolve(ISearchIndexRepository).enqueue_drifted(expectations)
        coverage = await self.refresh_coverage()
        # §10.4's pruning job, on its own much longer clock. The sweep is simply the only thing
        # that already runs on a timer, so it carries it rather than a second background task.
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
            # documents are built and the provider is called. §11 rule 9, and with a pool of five
            # connections shared with request traffic it is not a formality.
            async with self._scope_factory() as scope:
                rows = await scope.resolve(ISearchIndexRepository).load_rows(product_ids)

            documents = [build_document(row) for row in rows]

            # ---- outside every transaction ----
            vectors, embedding_error = await self._embed(rows, documents)
            # -----------------------------------

            writable = self._writable(rows, documents, failed=embedding_error is not None)

            async with self._scope_factory() as scope:
                repository = scope.resolve(ISearchIndexRepository)
                await repository.write_documents(writable, vectors)
                if embedding_error is None:
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
        """One batched provider call per configured slot, holding no database connection.

        Only the products whose slot is actually stale are sent. A fallback provider being
        reconfigured must not make the primary column re-embed, and `reindex_catalog --all` must
        not pay for 46 vectors that were already correct — §11 batches provider calls for cost,
        and re-sending current text is the same cost by another route.

        The first failing slot stops the run and is reported rather than raised, because the
        caller still has useful work to do with whatever succeeded. Vectors are keyed by product
        id: the batch sent excludes already-current products, so its positions and the claimed
        batch's positions are different lists, and pairing them by index is precisely how
        vectors end up stored against the wrong products.
        """
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
        """Which documents may be stored when a slot could not be embedded.

        With every slot embedded, all of them. With a provider down the answer splits, and the
        split is the difference between an index that heals itself and one that silently never
        gets a vector:

        - a product with **no** document yet is written anyway. Otherwise it is invisible to
          lexical search too, and coverage drops far enough to move the whole store from §12's
          step 3 to step 4 — a provider outage taking out the leg that does not need a provider.
          Its vector column stays NULL, and NULL is a drift condition, so the sweep comes back
          for it.
        - a product that **already has** a document is left entirely alone. Writing the new text
          without a new vector would make the stored hash current, and a current hash is what the
          sweep uses to decide the row is done — so the row would look finished for ever while
          holding a vector describing text that no longer exists.
        """
        if not failed:
            return list(documents)
        unindexed = {row.product_id for row in rows if not row.is_indexed}
        return [document for document in documents if document.product_id in unindexed]

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

    async def _fail(
        self, claimed: Sequence[ClaimedJobDTO], error_code: str, *, permanent: bool = False
    ) -> None:
        """Record the attempt against every job in the batch, in a scope of its own.

        It has to be a new scope: the failure that brought us here has already aborted the one
        that was open, and Postgres will run nothing else on that session.

        `permanent` implements §11 rule 6 — "mark permanent model/dimension errors for operator
        attention without retrying forever". A revoked key, a rejected model or a malformed
        response returns the same answer on every attempt, so spending five backoffs to reach it
        buys nothing and delays the row showing up in `failed_jobs`. The job is pushed straight
        to the attempt cap instead, where an operator sees it and `reindex_catalog --product-id`
        is the deliberate way back.
        """
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
            # The lease expires on its own, so the jobs come back regardless. Losing the error
            # code is not worth taking the worker down for.
            logger.warning("could not record index failures; leases will expire instead")

    async def prune_query_cache(self) -> int:
        """§10.4's pruning job, rate-limited to its own much longer clock.

        Called from the sweep, which runs every 20 seconds; the rows it collects live for a day.
        Running the delete every sweep would be 4,320 statements a day to reclaim what one
        reclaims.
        """
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
