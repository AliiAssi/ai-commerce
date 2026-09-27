from __future__ import annotations

from datetime import UTC, datetime, time

from app.application.jobs import db_keepalive, schedule
from app.core.scheduler import Scheduler, next_daily_run


def at(hour: int, minute: int = 0, day: int = 27) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def test_a_time_still_ahead_today_runs_today():
    assert next_daily_run(time(12, 0), at(9)) == at(12)


def test_a_time_already_passed_runs_tomorrow():
    assert next_daily_run(time(0, 0), at(23, 59)) == at(0, day=28)


def test_the_exact_due_moment_moves_to_tomorrow():
    assert next_daily_run(time(0, 0), at(0)) == at(0, day=28)


def test_db_keepalive_is_scheduled_daily_at_midnight():
    scheduler = Scheduler()
    schedule.register(scheduler)
    [job] = scheduler.jobs
    assert (job.name, job.at, job.job) == ("db_keepalive", time(0, 0), db_keepalive.run)


async def test_stop_cancels_pending_jobs():
    calls: list[str] = []

    async def job() -> None:
        calls.append("ran")

    scheduler = Scheduler()
    scheduler.daily_at("00:00", "noop", job)
    scheduler.start()
    await scheduler.stop()
    assert calls == []
