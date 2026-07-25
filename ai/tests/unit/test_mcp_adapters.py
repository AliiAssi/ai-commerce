from __future__ import annotations

import inspect

from mcp.server.fastmcp import FastMCP

from app.application.tools.registry import ToolRegistry
from app.presentation.mcp.tools import analytics, catalog, orders
from tests.unit.conftest import build_fake_registry


# a fake registry has the same specs as the real one, so the adapters register against it
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

    # drift guard: each adapter's parameters must cover its params-model fields, so the
    # MCP-advertised schema stays in step with what the registry validates
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
