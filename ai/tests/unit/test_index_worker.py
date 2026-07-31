from __future__ import annotations

import asyncio

import pytest

from app.application.dtos.index_dto import IndexCoverageDTO, IndexRunReportDTO, SweepReportDTO
from app.application.services.index_worker import IndexWorker
from app.core.index_state import IndexCoverage

EMPTY_COVERAGE = IndexCoverageDTO(active_products=0, documents=0)


class FakeIndexService:
    def __init__(self, *, batches: list[int] | None = None, raises: int = 0) -> None:
        self.sweeps = 0
        self.batches = 0
        self.released = 0
        self.refreshes = 0
        self._sizes = list(batches or [])
        self._raises = raises

    async def sweep(self) -> SweepReportDTO:
        self.sweeps += 1
        return SweepReportDTO(coverage=EMPTY_COVERAGE)

    async def refresh_coverage(self) -> IndexCoverageDTO:
        self.refreshes += 1
        return EMPTY_COVERAGE

    async def run_batch(self) -> IndexRunReportDTO:
        self.batches += 1
        if self._raises:
            self._raises -= 1
            raise RuntimeError("provider exploded")
        claimed = self._sizes.pop(0) if self._sizes else 0
        return IndexRunReportDTO(claimed=claimed, indexed=claimed)

    async def release_leases(self) -> int:
        self.released += 1
        return 3


class Config:
    SEARCH_INDEX_SWEEP_SECONDS = 3600.0
    SEARCH_INDEX_POLL_SECONDS = 0.01
    SEARCH_INDEX_BATCH_SIZE = 4
    SEARCH_INDEX_SHUTDOWN_SECONDS = 2.0


async def _run_briefly(worker: IndexWorker, *, until) -> None:
    worker.start()
    for _ in range(200):
        await asyncio.sleep(0.01)
        if until():
            break
    await worker.stop()


class TestCadence:
    async def test_the_first_iteration_sweeps(self):
        service = FakeIndexService()
        worker = IndexWorker(service, Config())

        await _run_briefly(worker, until=lambda: service.sweeps >= 1)

        assert service.sweeps == 1

    async def test_a_full_batch_is_followed_immediately_by_another(self):
        service = FakeIndexService(batches=[4, 4, 4])
        worker = IndexWorker(service, Config())

        await _run_briefly(worker, until=lambda: service.batches >= 4)

        assert service.batches >= 4

    async def test_a_drained_queue_settles_the_coverage_gate_without_waiting_for_a_sweep(self):
        service = FakeIndexService(batches=[4, 4, 2])
        worker = IndexWorker(service, Config())

        await _run_briefly(worker, until=lambda: service.refreshes >= 1)

        assert service.refreshes >= 1

    async def test_an_idle_poll_does_not_re_measure_coverage(self):
        service = FakeIndexService()
        worker = IndexWorker(service, Config())

        await _run_briefly(worker, until=lambda: service.batches >= 5)

        assert service.refreshes == 0


class TestResilience:
    async def test_one_failing_iteration_does_not_end_the_worker(self):
        service = FakeIndexService(raises=1)
        worker = IndexWorker(service, Config())

        await _run_briefly(worker, until=lambda: service.batches >= 3)

        assert service.batches >= 3

    async def test_stopping_releases_this_worker_leases(self):
        service = FakeIndexService()
        worker = IndexWorker(service, Config())

        await _run_briefly(worker, until=lambda: service.sweeps >= 1)

        assert service.released == 1

    async def test_stopping_a_worker_that_never_started_is_safe(self):
        service = FakeIndexService()

        await IndexWorker(service, Config()).stop()

        assert service.released == 0

    async def test_a_hung_iteration_is_cancelled_rather_than_blocking_shutdown(self):
        class Hanging(FakeIndexService):
            async def run_batch(self) -> IndexRunReportDTO:
                await asyncio.sleep(60)
                raise AssertionError("unreachable")

        class Impatient(Config):
            SEARCH_INDEX_SHUTDOWN_SECONDS = 0.05

        service = Hanging()
        worker = IndexWorker(service, Impatient())
        worker.start()
        await asyncio.sleep(0.05)

        await asyncio.wait_for(worker.stop(), timeout=5)

        assert service.released == 1


class TestCoverageState:
    @pytest.mark.parametrize(
        ("active", "documents", "ready"),
        [(46, 46, True), (46, 44, True), (46, 40, False), (46, 0, False)],
    )
    def test_readiness_follows_the_threshold(self, active, documents, ready):
        coverage = IndexCoverage()

        coverage.update(active_products=active, documents=documents, threshold=0.95)

        assert coverage.ready is ready

    def test_an_empty_catalog_is_not_ready(self):
        coverage = IndexCoverage()

        coverage.update(active_products=0, documents=0, threshold=0.95)

        assert coverage.ready is False

    def test_coverage_starts_not_ready(self):
        assert IndexCoverage().ready is False
