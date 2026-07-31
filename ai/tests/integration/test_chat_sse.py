from __future__ import annotations

import json
import os

import pytest

from tests.integration.conftest import INTERNAL_API_KEY

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


def _events(text: str) -> list[dict]:
    return [
        json.loads(line[len("data: ") :]) for line in text.splitlines() if line.startswith("data: ")
    ]


@pytest.fixture
def scripted_llm(app):
    from app.application.llm.illm_client import ILLMClient
    from app.core.container import container

    original = container.resolve(ILLMClient)

    def _install(script):
        from tests.unit.fakes import FakeLLMClient

        container.bind_instance(ILLMClient, FakeLLMClient(script))
        container._singletons.clear()

    yield _install

    container.bind_instance(ILLMClient, original)
    container._singletons.clear()


async def test_chat_streams_tool_then_tokens_then_done(client, catalog, scripted_llm) -> None:
    from tests.unit.fakes import answer_turn, tool_turn

    scripted_llm([tool_turn("search_products", query="tent"), answer_turn("Here is a tent")])

    response = await client.post(
        "/chat",
        json={"message": "find me a tent", "user_email": "shopper@test.com"},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
    )
    assert response.status_code == 200
    session_id = response.headers["X-Session-Id"]

    events = _events(response.text)
    types = [e["type"] for e in events]
    assert "tool" in types
    assert "token" in types
    assert types[-1] == "done"
    assert events[-1]["session_id"] == session_id


async def test_history_persists_across_two_turns(client, catalog, scripted_llm) -> None:
    from tests.unit.fakes import answer_turn

    scripted_llm([answer_turn("first answer")])
    first = await client.post(
        "/chat",
        json={"message": "hello", "user_email": "shopper@test.com"},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
    )
    session_id = first.headers["X-Session-Id"]

    scripted_llm([answer_turn("second answer")])
    second = await client.post(
        "/chat",
        json={"message": "again", "session_id": session_id, "user_email": "shopper@test.com"},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
    )
    assert second.status_code == 200
    assert second.headers["X-Session-Id"] == session_id

    from sqlalchemy import text

    from app.core.container import container

    async with container.session_factory() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM ai_chat_messages WHERE session_id = :sid"),
            {"sid": session_id},
        )
    assert count == 4


async def test_chat_requires_internal_key(client) -> None:
    response = await client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
