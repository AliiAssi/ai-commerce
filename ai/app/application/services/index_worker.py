from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from app.application.iservices.iindex_service import IIndexService
from app.core.config import Settings

logger = logging.getLogger(__name__)


class IndexWorker:
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
            with suppress(Exception):
                released = await self._service.release_leases()
                if released:
                    logger.info("released %d index lease(s) on shutdown", released)
        logger.info("search index worker stopped")

    async def _run(self) -> None:
        next_sweep = 0.0
        while not self._stop.is_set():
            delay = self._settings.SEARCH_INDEX_POLL_SECONDS
            try:
                if time.monotonic() >= next_sweep:
                    await self._service.sweep()
                    next_sweep = time.monotonic() + self._settings.SEARCH_INDEX_SWEEP_SECONDS
                report = await self._service.run_batch()
                if report.claimed >= self._settings.SEARCH_INDEX_BATCH_SIZE:
                    delay = 0.0
                elif report.claimed:
                    await self._service.refresh_coverage()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("search index worker iteration failed")
            if delay and await self._wait(delay):
                return
            await asyncio.sleep(0)

    async def _wait(self, seconds: float) -> bool:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return True
        return False
