from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from app.application.iservices.iindex_service import IIndexService
from app.core.config import Settings

logger = logging.getLogger(__name__)


class IndexWorker:
    """Runs the indexing pipeline for as long as this process lives (§11).

    All it owns is cadence: when to sweep, when to poll, and how to stop. Every rule that has a
    correctness consequence — claiming, leasing, backoff, what counts as finished — lives in
    `IndexService`, where it can be tested without a clock. This class exists because a loop
    that sleeps is the one thing a test cannot assert about cheaply.

    There is no SIGTERM handler here on purpose. Uvicorn already turns SIGTERM into a lifespan
    shutdown, and a second handler would race the first; `stop()` being called from the lifespan
    *is* §11 rule 8.
    """

    def __init__(self, service: IIndexService, settings: Settings) -> None:
        self._service = service
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="search-index-worker")
        logger.info(
            "search index worker started (sweep %.0fs, batch %d)",
            self._settings.SEARCH_INDEX_SWEEP_SECONDS,
            self._settings.SEARCH_INDEX_BATCH_SIZE,
        )

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(
                asyncio.shield(task), timeout=self._settings.SEARCH_INDEX_SHUTDOWN_SECONDS
            )
        except TimeoutError:
            logger.warning("search index worker did not stop in time; cancelling")
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        except Exception:
            logger.exception("search index worker stopped with an error")
        finally:
            # Hand the leases back rather than making the next deploy wait them out. Best
            # effort: if this fails the leases expire on their own.
            with suppress(Exception):
                released = await self._service.release_leases()
                if released:
                    logger.info("released %d index lease(s) on shutdown", released)
        logger.info("search index worker stopped")

    async def _run(self) -> None:
        # Zero means the first iteration sweeps, so a process that starts against an empty index
        # begins filling it immediately instead of after one sweep interval.
        next_sweep = 0.0
        while not self._stop.is_set():
            delay = self._settings.SEARCH_INDEX_POLL_SECONDS
            try:
                if time.monotonic() >= next_sweep:
                    await self._service.sweep()
                    next_sweep = time.monotonic() + self._settings.SEARCH_INDEX_SWEEP_SECONDS
                report = await self._service.run_batch()
                if report.claimed >= self._settings.SEARCH_INDEX_BATCH_SIZE:
                    # More work is waiting when a batch came back full, so do not sleep on it.
                    delay = 0.0
                elif report.claimed:
                    # The queue just drained. Settle the coverage gate here rather than waiting
                    # for the next sweep, or a fully rebuilt index sits unused — and search
                    # keeps answering from §12's step 4 — for up to a whole sweep interval.
                    # Observed on the first real run: 46/46 documents, gate still closed.
                    await self._service.refresh_coverage()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad iteration must not end the worker: §12 requires index-worker failure
                # not to take down the ordinary API, and this task lives in the same process.
                logger.exception("search index worker iteration failed")
            if delay and await self._wait(delay):
                return
            await asyncio.sleep(0)

    async def _wait(self, seconds: float) -> bool:
        """Sleep, but wake immediately on shutdown. True when it was a shutdown."""
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return True
        return False
