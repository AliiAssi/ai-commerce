from __future__ import annotations

import os

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.integration.conftest import MCP_BEARER_TOKEN

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

MCP_URL = "http://test/mcp"


def _asgi_client(app, token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )


def _session(app, token: str = MCP_BEARER_TOKEN):
    return streamable_http_client(MCP_URL, http_client=_asgi_client(app, token))


async def test_list_tools_and_call_search(app, catalog) -> None:
    async with (
        _session(app) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        tools = {t.name for t in (await session.list_tools()).tools}
        assert "search_products" in tools
        assert "store_stats" in tools

        result = await session.call_tool("search_products", {"query": "tent"})
        assert not result.isError
        assert "Alpha Tent" in str(result.content)


async def test_resources_and_prompts_are_listed(app, catalog) -> None:
    async with (
        _session(app) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        resources = {str(r.uri) for r in (await session.list_resources()).resources}
        assert "store://overview" in resources

        prompts = {p.name for p in (await session.list_prompts()).prompts}
        assert "shopping_assistant" in prompts


async def test_missing_bearer_is_rejected(app) -> None:
    with pytest.raises(Exception):  # noqa: B017 - any transport/protocol error is acceptable
        async with (
            _session(app, token="wrong-token") as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
