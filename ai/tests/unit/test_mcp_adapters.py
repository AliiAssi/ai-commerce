from __future__ import annotations

import inspect

from mcp.server.fastmcp import FastMCP

from app.application.tools.registry import ToolRegistry
from app.presentation.mcp.tools import analytics, catalog, orders
from tests.unit.conftest import build_fake_registry
from tests.unit.fakes import FakeProductReadRepository


def _register_all(mcp: FastMCP, registry: ToolRegistry) -> None:
    catalog.register(mcp, registry)
    orders.register(mcp, registry)
    analytics.register(mcp, registry)


async def test_adapters_register_every_tool_with_matching_schemas() -> None:
    registry = build_fake_registry()
    mcp = FastMCP("test", stateless_http=True, json_response=True)
    _register_all(mcp, registry)

    tools = {t.name: t for t in await mcp.list_tools()}
    assert set(tools) == {spec.name for spec in registry.specs()}

    for spec in registry.specs():
        schema_props = set(tools[spec.name].inputSchema.get("properties", {}))
        model_fields = set(spec.params_model.model_fields)
        assert model_fields <= schema_props, spec.name


def test_adapter_signatures_match_params_models() -> None:
    registry = build_fake_registry()
    adapters: dict[str, object] = {}

    class _Collector:
        def add_tool(self, fn, name, description) -> None:
            adapters[name] = fn

    collector = _Collector()
    catalog.register(collector, registry)
    orders.register(collector, registry)
    analytics.register(collector, registry)

    for spec in registry.specs():
        sig = inspect.signature(adapters[spec.name])
        assert set(spec.params_model.model_fields) <= set(sig.parameters), spec.name


def _adapters(registry: ToolRegistry, storefront_url: str) -> dict[str, object]:
    adapters: dict[str, object] = {}

    class _Collector:
        def add_tool(self, fn, name, description) -> None:
            adapters[name] = fn

    for module in (catalog, orders, analytics):
        module.register(_Collector(), registry, storefront_url)
    return adapters


async def test_results_carry_absolute_storefront_urls_when_configured() -> None:
    products = FakeProductReadRepository()
    tent = products.seed("Alpha Tent", category_slug="outdoor", review_count=1)
    registry = build_fake_registry(products=products)

    search = await _adapters(registry, "https://shop.example")["search_products"](query="tent")
    top = await _adapters(registry, "https://shop.example")["top_rated_products"]()
    bare = await _adapters(registry, "")["get_product"](product_id=tent.id)

    tracking = "utm_source=assistant&utm_medium=mcp"
    assert search["items"][0]["url"] == f"https://shop.example/products/{tent.id}?{tracking}"
    assert search["url"] == f"https://shop.example/catalog?q=tent&sort=rating&{tracking}"
    assert top["products"][0]["url"].startswith("https://shop.example/products/")
    assert "url" not in bare
