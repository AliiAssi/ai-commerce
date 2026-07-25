from __future__ import annotations

import pytest

from app.application.dtos.tool_dto import ToolContext
from app.core.exceptions import ToolExecutionError
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
    # Decimal serialized as an exact string, never a float
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

    # the model tries to peek at another customer by passing their email — it is ignored
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
