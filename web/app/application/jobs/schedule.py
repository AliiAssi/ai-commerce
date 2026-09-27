from __future__ import annotations

from app.application.jobs import db_keepalive
from app.core.scheduler import Scheduler


def register(scheduler: Scheduler) -> None:
    scheduler.daily_at("00:00", "db_keepalive", db_keepalive.run)
