from __future__ import annotations

import os

import pytest

from tests.integration.conftest import auth_headers, register_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


# a gateway that records what the proxy passed and returns canned SSE frames (no network)
class FakeAIGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def open_chat(self, message, session_id, user_email):
        from app.application.dtos.ai_dto import ChatStreamHandle

        self.calls.append({"message": message, "session_id": session_id, "user_email": user_email})

        async def frames():
            yield b'data: {"type":"token","text":"hi"}\n\n'
            yield b'data: {"type":"done","session_id":"sess-123"}\n\n'

        return ChatStreamHandle(session_id="sess-123", frames=frames())

    async def aclose(self) -> None:
        pass


@pytest.fixture
def fake_gateway(client):
    from app.application.iservices.iai_gateway import IAIGateway
    from app.core.container import container

    gateway = FakeAIGateway()
    container.bind_instance(IAIGateway, gateway)
    yield gateway
    container._instances.pop(IAIGateway, None)


async def test_guest_chat_streams_with_no_email(client, fake_gateway) -> None:
    response = await client.post("/api/v1/ai/chat", json={"message": "recommend a tent"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-session-id"] == "sess-123"
    assert '"type":"token"' in response.text
    # guest -> the proxy sends user_email=None, never a client-supplied value
    assert fake_gateway.calls[0]["user_email"] is None


async def test_logged_in_chat_uses_cookie_email(client, fake_gateway) -> None:
    token = await register_user(client, "ai-shopper@test.com")
    # cookie carries the session; the proxy derives the email server-side
    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "where is my order?"},
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert fake_gateway.calls[0]["user_email"] == "ai-shopper@test.com"


async def test_empty_message_is_rejected(client, fake_gateway) -> None:
    response = await client.post("/api/v1/ai/chat", json={"message": ""})
    assert response.status_code == 422
    assert fake_gateway.calls == []


async def test_oversized_message_is_rejected(client, fake_gateway) -> None:
    response = await client.post("/api/v1/ai/chat", json={"message": "x" * 2001})
    assert response.status_code == 422
    assert fake_gateway.calls == []
