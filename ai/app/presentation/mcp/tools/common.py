from __future__ import annotations

from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from app.application.dtos.tool_dto import ToolContext
from app.application.tools.registry import ToolRegistry
from app.core.exceptions import ToolExecutionError
from app.core.links import absolute, ref_path, tracked


def _add_urls(node: Any, storefront_url: str) -> None:
    if isinstance(node, list):
        for item in node:
            _add_urls(item, storefront_url)
    elif isinstance(node, dict):
        for value in list(node.values()):
            _add_urls(value, storefront_url)
        ref = node.get("ref")
        path = ref_path(ref) if isinstance(ref, str) else None
        if path:
            node["url"] = absolute(storefront_url, tracked(path, "mcp"))


async def run_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict[str, Any],
    context: ToolContext,
    storefront_url: str = "",
) -> dict[str, Any]:
    try:
        result = await registry.execute(name, arguments, context)
    except ToolExecutionError as exc:
        raise ToolError(exc.message) from exc
    if storefront_url:
        _add_urls(result, storefront_url)
    return result
