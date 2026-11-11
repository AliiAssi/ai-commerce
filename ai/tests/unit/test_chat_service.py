from __future__ import annotations

import logging
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
        LLM_API_KEY="k",
    )
    base.update(overrides)
    return Settings(**base)


class BrokenLLM:
    async def chat(self, messages, tools=None):
        raise LLMUnavailableError("down", retryable=True)

    async def stream(self, messages, tools=None):
        raise LLMUnavailableError("down", retryable=True)
        yield  # pragma: no cover - makes this an async generator


class QuotaExhaustedLLM:
    async def chat(self, messages, tools=None):
        raise LLMUnavailableError("402", quota_exhausted=True)

    async def stream(self, messages, tools=None):
        raise LLMUnavailableError("402", quota_exhausted=True)
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


async def test_llm_unavailable_is_logged_as_error(caplog: pytest.LogCaptureFixture) -> None:
    service, _ = _build(BrokenLLM())
    session = await service.resolve_session(None, None)

    with caplog.at_level(logging.ERROR, logger="app.application.services.chat_service"):
        await _collect(service, session, "hi")

    assert any(r.levelno == logging.ERROR for r in caplog.records)


async def test_quota_exhausted_shows_demo_limit_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.core.prompts import load_prompts

    service, _ = _build(QuotaExhaustedLLM())
    session = await service.resolve_session(None, None)

    with caplog.at_level(logging.ERROR, logger="app.application.services.chat_service"):
        events = await _collect(service, session, "hi")

    assert events == [
        ChatStreamEventDTO(
            type="error", message=load_prompts().render("errors.llm_quota_exhausted")
        )
    ]
    assert any("quota" in r.getMessage() for r in caplog.records)


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


async def test_cited_products_become_links_and_cards_and_persist_as_refs() -> None:
    products = FakeProductReadRepository()
    tent = products.seed("Alpha Tent", price="100.00", rating_avg="4.50", review_count=2)
    products.seed("Alpha Stove", price="40.00")
    llm = FakeLLMClient(
        [
            tool_turn("search_products", query="alpha", page_size=1),
            answer_turn(f"Try the [Alpha Tent](product:{tent.id}) and [Ghost](product:999)."),
        ]
    )
    service, chat = _build(llm, products=products)
    session = await service.resolve_session(None, None)

    events = await _collect(service, session, "something alpha")

    shown = "".join(e.text or "" for e in events if e.type == "token")
    tracking = "utm_source=assistant&utm_medium=chat"
    assert f"[Alpha Tent](/products/{tent.id}?{tracking})" in shown
    assert "Ghost" in shown
    assert "999" not in shown

    cards = next(e for e in events if e.type == "products")
    assert [c.id for c in cards.products] == [tent.id]
    assert cards.products[0].url == f"/products/{tent.id}?{tracking}"
    assert cards.more is not None
    assert cards.more.total == 2
    assert cards.more.url == f"/catalog?q=alpha&sort=rating&{tracking}"
    assert [e.type for e in events][-2:] == ["products", "done"]

    stored = await chat.list_messages(session.id)
    assert f"[Alpha Tent](product:{tent.id})" in stored[1].content
    assert "Ghost" in stored[1].content
    assert "999" not in stored[1].content


async def test_refs_from_an_earlier_turn_are_not_evidence() -> None:
    products = FakeProductReadRepository()
    tent = products.seed("Alpha Tent")
    llm = FakeLLMClient([answer_turn(f"The [Alpha Tent](product:{tent.id}) again.")])
    service, _ = _build(llm, products=products)
    session = await service.resolve_session(None, None)

    events = await _collect(service, session, "that tent again")

    shown = "".join(e.text or "" for e in events if e.type == "token")
    assert "/products/" not in shown
    assert "Alpha Tent" in shown
    assert not any(e.type == "products" for e in events)


async def test_category_and_order_refs_resolve_when_a_tool_returned_them() -> None:
    products = FakeProductReadRepository()
    products.seed("Alpha Tent", category="Outdoor", category_slug="outdoor")
    orders = FakeOrderReadRepository()
    mine = orders.seed("me@test.com")
    llm = FakeLLMClient(
        [
            tool_turn("list_categories"),
            tool_turn("get_order_status", order_id=mine.id),
            answer_turn(f"[Outdoor](category:outdoor) and [order #{mine.id}](order:{mine.id})."),
        ]
    )
    service, _ = _build(llm, products=products, orders=orders)
    session = await service.resolve_session(None, "me@test.com")

    events = await _collect(service, session, "categories and my order")

    shown = "".join(e.text or "" for e in events if e.type == "token")
    assert "[Outdoor](/catalog?category=outdoor&utm_source=assistant" in shown
    assert f"](/account/orders/{mine.id}?utm_source=assistant" in shown
    assert not any(e.type == "products" for e in events)
