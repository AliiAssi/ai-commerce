from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def _repo():
    from app.core.container import container
    from app.infrastructure.repositories.chat_repository import ChatRepository

    return container, ChatRepository


async def test_session_message_roundtrip(app) -> None:
    from app.application.dtos.chat_dto import ChatMessageDTO

    container, ChatRepository = await _repo()
    assert container.session_factory is not None

    async with container.session_factory() as session, session.begin():
        repo = ChatRepository(session)
        created = await repo.create_session("shopper@test.com")
        await repo.append_messages(
            created.id,
            [
                ChatMessageDTO(role="user", content="hi"),
                ChatMessageDTO(
                    role="assistant",
                    content="",
                    tool_calls=[{"name": "search_products", "arguments": {"query": "tent"}}],
                ),
            ],
        )

    async with container.session_factory() as session:
        repo = ChatRepository(session)
        fetched = await repo.get_session(created.id)
        messages = await repo.list_messages(created.id)
        count = await repo.count_messages(created.id)

    assert fetched is not None
    assert fetched.user_email == "shopper@test.com"
    assert count == 2
    assert messages[0].role == "user"
    assert messages[1].tool_calls[0]["name"] == "search_products"


async def test_history_grows_across_appends(app) -> None:
    from app.application.dtos.chat_dto import ChatMessageDTO

    container, ChatRepository = await _repo()
    async with container.session_factory() as session, session.begin():
        repo = ChatRepository(session)
        created = await repo.create_session(None)
        await repo.append_messages(created.id, [ChatMessageDTO(role="user", content="one")])
    async with container.session_factory() as session, session.begin():
        repo = ChatRepository(session)
        await repo.append_messages(created.id, [ChatMessageDTO(role="user", content="two")])

    async with container.session_factory() as session:
        repo = ChatRepository(session)
        assert await repo.count_messages(created.id) == 2


async def test_get_unknown_session_returns_none(app) -> None:
    container, ChatRepository = await _repo()
    async with container.session_factory() as session:
        repo = ChatRepository(session)
        assert await repo.get_session(uuid.uuid4()) is None
