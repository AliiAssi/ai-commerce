from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.application.dtos.chat_dto import ChatStreamEventDTO
from app.application.services.chat_service import ChatService
from app.application.tools.registry import ToolRegistry
from app.core.config import Settings
from app.core.exceptions import LLMUnavailableError
from app.infrastructure.irepositories.ichat_repository import IChatRepository
from app.infrastructure.irepositories.iorder_read_repository import IOrderReadRepository
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository
from app.infrastructure.irepositories.ireview_read_repository import IReviewReadRepository
from tests.unit.conftest import FakeScope
from tests.unit.fakes import (
    FakeChatRepository,
    FakeLLMClient,
    FakeOrderReadRepository,
    FakeProductReadRepository,
    FakeReviewReadRepository,
    answer_turn,
    tool_turn,
)


def _settings(**overrides) -> Settings:
    base = dict(
        DATABASE_URL="postgresql://u:p@h/db",
        INTERNAL_API_KEY="x" * 16,
        MCP_BEARER_TOKEN="y" * 16,
        OLLAMA_API_KEY="k",
    )
    base.update(overrides)
    return Settings(**base)


class BrokenLLM:
    async def chat(self, messages, tools=None):
        raise LLMUnavailableError("down", retryable=True)

    async def stream(self, messages, tools=None):
        raise LLMUnavailableError("down", retryable=True)
        yield  # pragma: no cover - makes this an async generator


def _build(
    llm,
    *,
    settings: Settings | None = None,
    products: FakeProductReadRepository | None = None,
    orders: FakeOrderReadRepository | None = None,
    chat: FakeChatRepository | None = None,
) -> tuple[ChatService, FakeChatRepository]:
    from app.application.events.bus import EventBus
    from app.application.tools.bootstrap import build_tool_registry

    chat = chat or FakeChatRepository()
    bindings = {
        IProductReadRepository: products or FakeProductReadRepository(),
        IOrderReadRepository: orders or FakeOrderReadRepository(),
        IReviewReadRepository: FakeReviewReadRepository(),
        IChatRepository: chat,
    }
    scope = FakeScope(bindings)

    @asynccontextmanager
    async def scope_factory() -> AsyncIterator[FakeScope]:
        yield scope

    from app.core.prompts import load_prompts

    settings = settings or _settings()
    registry: ToolRegistry = build_tool_registry(scope_factory=scope_factory)
    service = ChatService(
        llm, registry, load_prompts(), settings, EventBus(), scope_factory=scope_factory
    )
    return service, chat


async def _collect(service, session, message) -> list[ChatStreamEventDTO]:
    return [e async for e in service.stream_reply(session, message)]


async def test_direct_answer_streams_tokens_and_persists() -> None:
    service, chat = _build(FakeLLMClient([answer_turn("Hello there friend")]))
    session = await service.resolve_session(None, "me@test.com")

    events = await _collect(service, session, "hi")

    assert [e.type for e in events] == ["token", "token", "token", "done"]
    assert events[-1].session_id == session.id
    stored = await chat.list_messages(session.id)
    assert [m.role for m in stored] == ["user", "assistant"]
    assert stored[1].content.strip() == "Hello there friend"


async def test_tool_call_then_answer() -> None:
    products = FakeProductReadRepository()
    products.seed("Alpha Tent", price="100.00")
    llm = FakeLLMClient([tool_turn("search_products", query="tent"), answer_turn("Found it")])
    service, _ = _build(llm, products=products)
    session = await service.resolve_session(None, None)

    events = await _collect(service, session, "find a tent")
    types = [e.type for e in events]

    assert types[0] == "tool"
    assert events[0].name == "search_products"
    assert "token" in types
    assert types[-1] == "done"


async def test_order_tool_uses_session_email_not_model_supplied() -> None:
    orders = FakeOrderReadRepository()
    mine = orders.seed("me@test.com")
    orders.seed("other@test.com")
    llm = FakeLLMClient(
        [tool_turn("get_order", order_id=mine.id, user_email="other@test.com"), answer_turn("ok")]
    )
    service, _ = _build(llm, orders=orders)
    session = await service.resolve_session(None, "me@test.com")

    events = await _collect(service, session, "where is my order")
    assert any(e.type == "tool" and e.name == "get_order" for e in events)
    assert events[-1].type == "done"


async def test_llm_unavailable_yields_single_error() -> None:
    service, chat = _build(BrokenLLM())
    session = await service.resolve_session(None, None)

    events = await _collect(service, session, "hi")

    assert len(events) == 1
    assert events[0].type == "error"
    assert await chat.count_messages(session.id) == 0


async def test_loop_cap_yields_error() -> None:
    products = FakeProductReadRepository()
    products.seed("Alpha Tent")
    llm = FakeLLMClient([tool_turn("search_products", query="tent") for _ in range(10)])
    service, _ = _build(llm, settings=_settings(MAX_TOOL_ITERATIONS=2), products=products)
    session = await service.resolve_session(None, None)

    events = await _collect(service, session, "loop")
    assert events[-1].type == "error"


async def test_blank_model_reply_becomes_a_fallback_message() -> None:
    service, chat = _build(FakeLLMClient([answer_turn("   ")]))
    session = await service.resolve_session(None, None)

    events = await _collect(service, session, "hi")

    assert events[-1].type == "done"
    stored = await chat.list_messages(session.id)
    assert stored[1].content.strip()
    assert any(e.type == "token" and "rephrase" in (e.text or "") for e in events)


async def test_session_cap_rejects_before_llm() -> None:
    chat = FakeChatRepository()
    service, _ = _build(
        FakeLLMClient([answer_turn("hi")]),
        settings=_settings(MAX_MESSAGES_PER_SESSION=2),
        chat=chat,
    )
    session = await service.resolve_session(None, None)
    from app.application.dtos.chat_dto import ChatMessageDTO

    await chat.append_messages(
        session.id,
        [ChatMessageDTO(role="user", content="a"), ChatMessageDTO(role="assistant", content="b")],
    )

    events = await _collect(service, session, "third")
    assert len(events) == 1
    assert events[0].type == "error"


async def test_unknown_session_id_is_rejected() -> None:
    import uuid

    from app.core.exceptions import SessionNotFoundError

    service, _ = _build(FakeLLMClient([]))
    with pytest.raises(SessionNotFoundError):
        await service.resolve_session(uuid.uuid4(), None)


async def test_reusing_session_under_different_email_mints_new_session() -> None:
    chat = FakeChatRepository()
    service, _ = _build(FakeLLMClient([]), chat=chat)

    alice = await service.resolve_session(None, "alice@test.com")
    bob = await service.resolve_session(alice.id, "bob@test.com")

    assert bob.id != alice.id
    assert bob.user_email == "bob@test.com"


async def test_reusing_own_session_is_preserved() -> None:
    chat = FakeChatRepository()
    service, _ = _build(FakeLLMClient([]), chat=chat)

    first = await service.resolve_session(None, "alice@test.com")
    again = await service.resolve_session(first.id, "  Alice@Test.com ")

    assert again.id == first.id
