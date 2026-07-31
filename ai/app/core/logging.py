from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_access_logger = logging.getLogger("app.access")
_llm_usage_logger = logging.getLogger("app.llm.usage")


class _DevFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get()
        return super().format(record)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(environment: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if environment == "production":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            _DevFormatter(
                "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [handler]


def log_llm_usage(
    model: str, prompt_tokens: int, completion_tokens: int, duration_ms: float
) -> None:
    _llm_usage_logger.info(
        "model=%s prompt_tokens=%s completion_tokens=%s duration_ms=%.0f",
        model,
        prompt_tokens,
        completion_tokens,
        duration_ms,
    )


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = {k.decode("latin-1").lower(): v for k, v in scope.get("headers", [])}
        request_id = incoming.get(b"x-request-id", b"").decode("latin-1") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            _access_logger.info(
                "%s %s -> %s (%.1f ms)",
                scope.get("method"),
                scope.get("path"),
                status_code,
                duration_ms,
            )
            request_id_var.reset(token)
