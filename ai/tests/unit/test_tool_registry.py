from __future__ import annotations

import pytest

from app.application.dtos.tool_dto import ToolContext
from app.core.exceptions import ToolExecutionError
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository
from tests.unit.conftest import build_fake_registry
from tests.unit.fakes import FakeOrderReadRepository, FakeProductReadRepository

CHAT = ToolContext(source="chat", user_email="me@test.com")
MCP = ToolContext(source="mcp")


async def test_search_products_happy_path() -> None:
    products = FakeProductReadRepository()
    products.seed("Alpha Tent", price="100.00", rating_avg="4.50", review_count=3)
    registry = build_fake_registry(products=products)

    result = await registry.execute("search_products", {"query": "tent"}, MCP)

    assert result["total"] == 1
    assert result["items"][0]["name"] == "Alpha Tent"
    assert result["items"][0]["price"] == "100.00"


async def test_bad_input_becomes_clean_tool_error() -> None:
    registry = build_fake_registry()
    with pytest.raises(ToolExecutionError) as exc:
        await registry.execute("search_products", {"page_size": 999}, MCP)
    assert "invalid arguments for search_products" in exc.value.message
    assert "page_size" in exc.value.message


async def test_unknown_tool_raises() -> None:
    registry = build_fake_registry()
    with pytest.raises(ToolExecutionError, match="unknown tool"):
        await registry.execute("nope", {}, MCP)


async def test_chat_scope_overrides_model_supplied_email() -> None:
    orders = FakeOrderReadRepository()
    mine = orders.seed("me@test.com")
    orders.seed("someone@test.com")
    registry = build_fake_registry(orders=orders)

    result = await registry.execute(
        "get_order", {"order_id": mine.id, "user_email": "someone@test.com"}, CHAT
    )
    assert result["user_email"] == "me@test.com"


async def test_chat_without_signed_in_customer_is_refused() -> None:
    orders = FakeOrderReadRepository()
    order = orders.seed("me@test.com")
    registry = build_fake_registry(orders=orders)

    result = await registry.execute(
        "get_order", {"order_id": order.id}, ToolContext(source="chat", user_email=None)
    )
    assert "signed-in customer" in result["error"]


async def test_mcp_edge_passes_client_email_through() -> None:
    orders = FakeOrderReadRepository()
    order = orders.seed("client@test.com")
    registry = build_fake_registry(orders=orders)

    result = await registry.execute(
        "get_order", {"order_id": order.id, "user_email": "client@test.com"}, MCP
    )
    assert result["user_email"] == "client@test.com"


def test_ollama_tools_schema_shape() -> None:
    registry = build_fake_registry()
    specs = registry.ollama_tools()
    names = {t["function"]["name"] for t in specs}
    assert {
        "search_products",
        "get_product",
        "list_categories",
        "get_order",
        "list_orders",
        "get_order_status",
        "store_stats",
        "top_rated_products",
        "low_stock_products",
    } <= names
    search = next(t for t in specs if t["function"]["name"] == "search_products")
    assert search["type"] == "function"
    assert search["function"]["parameters"]["type"] == "object"
    assert "query" in search["function"]["parameters"]["properties"]


async def test_search_tool_holds_no_scope_while_the_search_service_runs() -> None:
    """§11 rule 9: the pool is five connections, and searching calls a model provider."""
    from contextlib import asynccontextmanager

    from app.application.dtos.search_dto import SearchResultDTO
    from app.application.tools.bootstrap import build_tool_registry
    from tests.unit.conftest import FakeScope

    open_scopes = 0
    open_while_searching: list[int] = []

    products = FakeProductReadRepository()
    products.seed("Alpha Tent", price="100.00", rating_avg="4.50", review_count=3)
    scope = FakeScope({IProductReadRepository: products})

    @asynccontextmanager
    async def scope_factory():
        nonlocal open_scopes
        open_scopes += 1
        try:
            yield scope
        finally:
            open_scopes -= 1

    class _Search:
        async def search(self, query):
            open_while_searching.append(open_scopes)
            return SearchResultDTO(
                product_ids=[p.id for p in products._products],
                total=1,
                page=1,
                page_size=10,
                query=query.q,
                language="en",
                mode="hybrid",
                reranked=False,
                effective_sort="relevance",
                degraded=False,
                parser_version="p",
                lexicon_version=1,
                ranker_version="r",
            )

    registry = build_tool_registry(scope_factory=scope_factory, search=_Search())
    result = await registry.execute("search_products", {"query": "tent"}, MCP)

    assert open_while_searching == [0], (
        "a database connection was held while the search service called its embedding provider"
    )
    assert result["items"][0]["name"] == "Alpha Tent"
    assert result["search"]["mode"] == "hybrid"
