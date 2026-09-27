from __future__ import annotations

import io
import logging
import sys
import threading
import urllib.error
from email.message import Message
from types import SimpleNamespace

from app.core.alerts import (
    Alert,
    AlertDispatcher,
    AlertHandler,
    AlertThrottle,
    DiscordWebhook,
    Occurrence,
    fingerprint,
    install_alerts,
    occurrence_from,
    redact,
    render,
)


def occ(key: str = "a", summary: str = "boom", detail: str = "boom") -> Occurrence:
    return Occurrence(key, "ERROR", "app.test", summary, detail, "req-1")


def record(msg: str, *args, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord("app.test", logging.ERROR, __file__, 1, msg, args, exc_info)


def raised(exc: BaseException):
    try:
        raise exc
    except BaseException:
        return sys.exc_info()


def test_first_occurrence_alerts_immediately():
    assert AlertThrottle(900).observe(occ(), 0) == Alert("new", occ())


def test_repeats_inside_the_window_are_counted_not_sent():
    throttle = AlertThrottle(900)
    throttle.observe(occ(), 0)
    assert [throttle.observe(occ(), at) for at in (5, 10, 15)] == [None, None, None]
    assert throttle.due(899) == []
    assert throttle.due(900) == [Alert("repeating", occ(), 3)]


def test_a_problem_that_stops_repeating_reports_quiet_once():
    throttle = AlertThrottle(900)
    throttle.observe(occ(), 0)
    throttle.observe(occ(), 5)
    throttle.due(900)
    assert throttle.due(1800) == [Alert("quiet", occ())]
    assert throttle.due(2700) == []


def test_a_one_off_expires_silently_and_is_news_again_later():
    throttle = AlertThrottle(900)
    throttle.observe(occ(), 0)
    assert throttle.due(900) == []
    assert throttle.observe(occ(), 901) == Alert("new", occ())


def test_different_problems_are_tracked_separately():
    throttle = AlertThrottle(900)
    assert throttle.observe(occ("a"), 0) is not None
    assert throttle.observe(occ("b"), 1) is not None


def test_drain_flushes_pending_repeats():
    throttle = AlertThrottle(900)
    for at in (0, 1, 2):
        throttle.observe(occ(), at)
    assert throttle.drain() == [Alert("repeating", occ(), 2)]


def test_fingerprint_groups_by_message_template_not_arguments():
    assert fingerprint(record("attempt %s failed", 1)) == fingerprint(
        record("attempt %s failed", 2)
    )


def test_fingerprint_separates_exception_types():
    key_error = fingerprint(record("failed", exc_info=raised(KeyError("x"))))
    value_error = fingerprint(record("failed", exc_info=raised(ValueError("x"))))
    assert key_error != value_error


def test_credentials_in_urls_are_masked():
    assert (
        redact("cannot reach postgresql://postgres.ref:s3cret@host:5432/db")
        == "cannot reach postgresql://***@host:5432/db"
    )


def test_occurrence_summarises_the_first_line_and_keeps_the_traceback():
    occurrence = occurrence_from(
        record("worker failed\nsecond line", exc_info=raised(RuntimeError("kaput")))
    )
    assert occurrence.summary == "worker failed"
    assert "RuntimeError: kaput" in occurrence.detail


def test_rendered_alert_fits_discord_limits_and_cannot_mention_anyone():
    huge = occ(summary="x" * 500, detail="y\n" * 5000)
    payload = render(
        Alert("new", huge), service="web", environment="production", window_seconds=900
    )
    embed = payload["embeds"][0]
    assert len(embed["title"]) <= 256
    assert len(embed["description"]) <= 4096
    assert payload["allowed_mentions"] == {"parse": []}


def test_repeating_and_quiet_alerts_say_what_happened():
    def embed(alert: Alert) -> dict:
        return render(alert, service="ai", environment="production", window_seconds=900)["embeds"][
            0
        ]

    repeating = embed(Alert("repeating", occ(), 179))
    assert repeating["title"] == "ai · still happening: boom"
    assert repeating["description"].startswith("179 more in the last 15 min")
    quiet = embed(Alert("quiet", occ()))
    assert quiet["title"] == "ai · quiet: boom"
    assert quiet["color"] != repeating["color"]


class FakeOpener:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, request, timeout):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(b"")


def http_error(code: int, retry_after: float | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://discord.test", code, "error", headers, None)


def test_webhook_waits_out_a_rate_limit_then_delivers():
    sleeps: list[float] = []
    opener = FakeOpener(http_error(429, 2.5), "ok")
    webhook = DiscordWebhook("https://discord.test", opener=opener, sleep=sleeps.append)
    assert webhook.send({"content": "x"}) is True
    assert (sleeps, opener.calls) == ([2.5], 2)


def test_webhook_failures_never_raise():
    failing = (http_error(500), urllib.error.URLError("down"), TimeoutError())
    for failure in failing:
        webhook = DiscordWebhook("https://discord.test", opener=FakeOpener(failure))
        assert webhook.send({"content": "x"}) is False


def test_the_alert_thread_cannot_alert_about_itself():
    submitted: list[Occurrence] = []
    dispatcher = SimpleNamespace(thread_id=threading.get_ident(), submit=submitted.append)
    AlertHandler(dispatcher, "WARNING").handle(record("alert delivery failed"))
    assert submitted == []


def test_alerts_are_off_without_a_webhook():
    assert install_alerts(SimpleNamespace(ALERTS_DISCORD_WEBHOOK_URL=""), "web") is None


def test_logged_errors_reach_the_webhook_grouped():
    sent: list[dict] = []
    dispatcher = AlertDispatcher(
        sent.append,
        AlertThrottle(900),
        lambda alert: {"kind": alert.kind, "count": alert.count},
        tick_seconds=0.01,
    )
    dispatcher.start()
    handler = AlertHandler(dispatcher, "WARNING")
    log = logging.getLogger("tests.alerts")
    log.addHandler(handler)
    try:
        log.info("below the threshold")
        for attempt in range(3):
            log.error("attempt %s failed", attempt)
    finally:
        log.removeHandler(handler)
        dispatcher.close()
    assert sent == [{"kind": "new", "count": 1}, {"kind": "repeating", "count": 2}]


def test_request_field_only_appears_when_there_was_a_request():
    def field_names(request_id: str) -> list[str]:
        occurrence = Occurrence("a", "ERROR", "app.test", "boom", "boom", request_id)
        payload = render(
            Alert("new", occurrence), service="web", environment="production", window_seconds=900
        )
        return [field["name"] for field in payload["embeds"][0]["fields"]]

    assert "Request" in field_names("539cfdd3752e")
    assert "Request" not in field_names("-")
