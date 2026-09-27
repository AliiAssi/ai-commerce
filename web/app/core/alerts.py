from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.config import Settings
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

# uvicorn's logger does not propagate to root, and it is where an error inside a streaming
# response body ends up once the headers are already sent.
_WATCHED_LOGGERS = ("", "uvicorn")

_COLORS = {"WARNING": 0xF5A524, "ERROR": 0xE5484D, "CRITICAL": 0xE5484D}
_QUIET_COLOR = 0x46A758
_TITLE_LIMIT = 256
_DESCRIPTION_LIMIT = 4096
_DETAIL_LINES = 25
_MAX_ATTEMPTS = 3
_MAX_RETRY_AFTER_SECONDS = 30.0
_CREDENTIALS = re.compile(r"://[^/\s:@]+:[^@\s]+@")
_NO_REQUEST = "-"


@dataclass(frozen=True)
class Occurrence:
    fingerprint: str
    level: str
    logger: str
    summary: str
    detail: str
    request_id: str


@dataclass(frozen=True)
class Alert:
    kind: Literal["new", "repeating", "quiet"]
    occurrence: Occurrence
    count: int = 1


@dataclass
class _Incident:
    latest: Occurrence
    window_start: float
    repeats: int = 0
    repeated: bool = False


class AlertThrottle:
    def __init__(self, cooldown_seconds: float) -> None:
        self._cooldown = cooldown_seconds
        self._incidents: dict[str, _Incident] = {}

    def observe(self, occurrence: Occurrence, now: float) -> Alert | None:
        incident = self._incidents.get(occurrence.fingerprint)
        if incident is None:
            self._incidents[occurrence.fingerprint] = _Incident(occurrence, now)
            return Alert("new", occurrence)
        incident.latest = occurrence
        incident.repeats += 1
        return None

    def due(self, now: float) -> list[Alert]:
        alerts: list[Alert] = []
        for key, incident in list(self._incidents.items()):
            if now - incident.window_start < self._cooldown:
                continue
            if incident.repeats:
                alerts.append(Alert("repeating", incident.latest, incident.repeats))
                incident.window_start, incident.repeats, incident.repeated = now, 0, True
            else:
                del self._incidents[key]
                if incident.repeated:
                    alerts.append(Alert("quiet", incident.latest))
        return alerts

    def drain(self) -> list[Alert]:
        pending = [
            Alert("repeating", incident.latest, incident.repeats)
            for incident in self._incidents.values()
            if incident.repeats
        ]
        self._incidents.clear()
        return pending


def fingerprint(record: logging.LogRecord) -> str:
    template = record.msg if isinstance(record.msg, str) else type(record.msg).__name__
    exc_type = record.exc_info[0] if record.exc_info else None
    return "|".join(
        (record.name, record.levelname, template, exc_type.__name__ if exc_type else "")
    )


def redact(text: str) -> str:
    return _CREDENTIALS.sub("://***@", text)


def occurrence_from(record: logging.LogRecord) -> Occurrence:
    message = record.getMessage()
    detail = message
    if record.exc_info:
        detail = f"{message}\n{logging.Formatter().formatException(record.exc_info)}"
    summary = message.splitlines()[0] if message.strip() else record.levelname
    return Occurrence(
        fingerprint=fingerprint(record),
        level=record.levelname,
        logger=record.name,
        summary=redact(summary),
        detail=redact(detail),
        request_id=request_id_var.get(),
    )


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _code_block(text: str) -> str:
    lines = text.replace("```", "`​``").splitlines()[-_DETAIL_LINES:]
    body = "\n".join(lines)[-(_DESCRIPTION_LIMIT - 8) :]
    return f"```\n{body}\n```"


def render(
    alert: Alert, *, service: str, environment: str, window_seconds: float
) -> dict[str, Any]:
    occurrence = alert.occurrence
    minutes = max(1, round(window_seconds / 60))
    color = _COLORS.get(occurrence.level, _COLORS["WARNING"])
    if alert.kind == "new":
        title = f"{service} · {occurrence.summary}"
        description = _code_block(occurrence.detail)
    elif alert.kind == "repeating":
        title = f"{service} · still happening: {occurrence.summary}"
        description = f"{alert.count} more in the last {minutes} min. Latest:\n" + _code_block(
            occurrence.detail
        )
    else:
        title = f"{service} · quiet: {occurrence.summary}"
        description = f"No repeats for {minutes} min."
        color = _QUIET_COLOR
    return {
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": _clip(title, _TITLE_LIMIT),
                "description": _clip(description, _DESCRIPTION_LIMIT),
                "color": color,
                "fields": [
                    {"name": "Level", "value": occurrence.level, "inline": True},
                    {"name": "Environment", "value": environment, "inline": True},
                    *(
                        [{"name": "Request", "value": occurrence.request_id, "inline": True}]
                        if occurrence.request_id != _NO_REQUEST
                        else []
                    ),
                    {"name": "Logger", "value": _clip(occurrence.logger, 1024)},
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ],
    }


# urllib rather than httpx: httpx logs every request URL at INFO, and this URL is a secret.
class DiscordWebhook:
    def __init__(
        self,
        url: str,
        *,
        timeout: float = 5.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._open = opener
        self._sleep = sleep

    def send(self, payload: dict[str, Any]) -> bool:
        body = json.dumps(payload).encode()
        for _ in range(_MAX_ATTEMPTS):
            request = urllib.request.Request(
                self._url,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "DiscordBot (beit, 1)"},
            )
            try:
                with self._open(request, timeout=self._timeout):
                    return True
            except urllib.error.HTTPError as exc:
                if exc.code != 429:
                    logger.warning("alert delivery failed: HTTP %s", exc.code)
                    return False
                self._sleep(_retry_after(exc))
            except OSError as exc:
                logger.warning("alert delivery failed: %s", exc.__class__.__name__)
                return False
        logger.warning("alert delivery failed: still rate limited")
        return False


def _retry_after(exc: urllib.error.HTTPError) -> float:
    with suppress(TypeError, ValueError):
        return min(float(exc.headers.get("Retry-After", 1.0)), _MAX_RETRY_AFTER_SECONDS)
    return 1.0


class AlertDispatcher:
    def __init__(
        self,
        send: Callable[[dict[str, Any]], object],
        throttle: AlertThrottle,
        render_alert: Callable[[Alert], dict[str, Any]],
        *,
        clock: Callable[[], float] = time.monotonic,
        tick_seconds: float = 1.0,
        capacity: int = 1000,
    ) -> None:
        self._send = send
        self._throttle = throttle
        self._render = render_alert
        self._clock = clock
        self._tick = tick_seconds
        self._queue: queue.Queue[Occurrence] = queue.Queue(maxsize=capacity)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="alerts", daemon=True)

    @property
    def thread_id(self) -> int | None:
        return self._thread.ident

    def start(self) -> None:
        self._thread.start()

    def submit(self, occurrence: Occurrence) -> None:
        with suppress(queue.Full):
            self._queue.put_nowait(occurrence)

    def close(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            try:
                occurrence: Occurrence | None = self._queue.get(timeout=self._tick)
            except queue.Empty:
                occurrence = None
            now = self._clock()
            if occurrence is not None and (alert := self._throttle.observe(occurrence, now)):
                self._deliver(alert)
            for alert in self._throttle.due(now):
                self._deliver(alert)
            if self._stop.is_set() and self._queue.empty():
                break
        for alert in self._throttle.drain():
            self._deliver(alert)

    def _deliver(self, alert: Alert) -> None:
        try:
            self._send(self._render(alert))
        except Exception:
            logger.exception("alert delivery crashed")


class AlertHandler(logging.Handler):
    def __init__(self, dispatcher: AlertDispatcher, level: str) -> None:
        super().__init__(level)
        self._dispatcher = dispatcher

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread == self._dispatcher.thread_id:
            return
        try:
            self._dispatcher.submit(occurrence_from(record))
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        for name in _WATCHED_LOGGERS:
            logging.getLogger(name).removeHandler(self)
        self._dispatcher.close()
        super().close()


def install_alerts(settings: Settings, service: str) -> AlertHandler | None:
    if not settings.ALERTS_DISCORD_WEBHOOK_URL:
        return None
    dispatcher = AlertDispatcher(
        DiscordWebhook(settings.ALERTS_DISCORD_WEBHOOK_URL).send,
        AlertThrottle(settings.ALERTS_COOLDOWN_SECONDS),
        lambda alert: render(
            alert,
            service=service,
            environment=settings.ENVIRONMENT,
            window_seconds=settings.ALERTS_COOLDOWN_SECONDS,
        ),
    )
    dispatcher.start()
    handler = AlertHandler(dispatcher, settings.ALERTS_MIN_LEVEL)
    for name in _WATCHED_LOGGERS:
        logging.getLogger(name).addHandler(handler)
    return handler
