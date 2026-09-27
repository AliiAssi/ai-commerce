from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

logger = logging.getLogger(__name__)

Job = Callable[[], Awaitable[None]]


def next_daily_run(at: time, after: datetime) -> datetime:
    candidate = datetime.combine(after.date(), at, tzinfo=UTC)
    return candidate if candidate > after else candidate + timedelta(days=1)


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    at: time
    job: Job


class Scheduler:
    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def jobs(self) -> list[ScheduledJob]:
        return list(self._jobs)

    def daily_at(self, at: str, name: str, job: Job) -> None:
        self._jobs.append(ScheduledJob(name, time.fromisoformat(at), job))

    def start(self) -> None:
        if self._tasks:
            return
        for scheduled in self._jobs:
            self._tasks.append(
                asyncio.create_task(self._run(scheduled), name=f"schedule:{scheduled.name}")
            )
            logger.info("scheduled %s daily at %s UTC", scheduled.name, scheduled.at)

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task

    async def _run(self, scheduled: ScheduledJob) -> None:
        due = next_daily_run(scheduled.at, datetime.now(UTC))
        while True:
            await asyncio.sleep(max(0.0, (due - datetime.now(UTC)).total_seconds()))
            try:
                await scheduled.job()
            except Exception:
                logger.exception("scheduled job %s failed", scheduled.name)
            due = next_daily_run(scheduled.at, max(due, datetime.now(UTC)))
