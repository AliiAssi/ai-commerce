from __future__ import annotations

import json

import httpx

from app.application.services.ai_gateway import AIGateway
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://u:p@h/db",
        JWT_SECRET="x" * 32,
        AI_SERVICE_URL="http://ai.test",
        INTERNAL_API_KEY="internal-key",
    )


def _gateway(handler) -> AIGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AIGateway(_settings(), client=client)


async def _collect(handle) -> str:
    chunks = [chunk async for chunk in handle.frames]
    return b"".join(chunks).decode()


async def test_happy_stream_passthrough_and_session_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # the proxy must attach the internal key and forward the trusted email
        assert request.headers["x-internal-key"] == "internal-key"
        assert json.loads(request.content)["user_email"] == "shopper@test.com"
        body = 'data: {"type":"token","text":"hi"}\n\ndata: {"type":"done","session_id":"abc"}\n\n'
        return httpx.Response(200, headers={"x-session-id": "abc"}, text=body)

    handle = await _gateway(handler).open_chat("hello", None, "shopper@test.com")
    assert handle.session_id == "abc"
    text = await _collect(handle)
    assert '"type":"token"' in text
    assert '"type":"done"' in text


async def test_unreachable_ai_yields_single_error_frame() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    handle = await _gateway(handler).open_chat("hello", None, None)
    assert handle.session_id is None
    text = await _collect(handle)
    assert '"type": "error"' in text
    assert "unavailable" in text


async def test_non_200_yields_error_frame() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="nope")

    handle = await _gateway(handler).open_chat("hello", None, None)
    assert handle.session_id is None
    text = await _collect(handle)
    assert '"type": "error"' in text


async def test_cold_instance_connect_failure_is_retried_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("still booting", request=request)
        return httpx.Response(200, text='data: {"type":"token","text":"hi"}\n\n')

    handle = await _gateway(handler).open_chat("hello", None, None)
    assert attempts == 2
    assert '"type":"token"' in await _collect(handle)


async def test_cold_instance_502_is_retried_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(200, text='data: {"type":"token","text":"hi"}\n\n')

    handle = await _gateway(handler).open_chat("hello", None, None)
    assert attempts == 2
    assert '"type":"token"' in await _collect(handle)


async def test_client_error_is_not_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, text="nope")

    handle = await _gateway(handler).open_chat("hello", None, None)
    assert attempts == 1
    assert '"type": "error"' in await _collect(handle)


async def test_retry_exhaustion_yields_error_frame() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("down", request=request)

    handle = await _gateway(handler).open_chat("hello", None, None)
    assert attempts == 2
    assert "unavailable" in await _collect(handle)


async def test_warm_pings_healthz_and_throttles_repeats() -> None:
    pings: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pings.append(str(request.url))
        return httpx.Response(200, json={"status": "ok"})

    gateway = _gateway(handler)
    await gateway.warm()
    await gateway.warm()

    assert pings == ["http://ai.test/healthz"]


async def test_warm_swallows_a_sleeping_instance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("booting", request=request)

    await _gateway(handler).warm()  # must not raise
