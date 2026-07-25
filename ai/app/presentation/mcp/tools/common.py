from __future__ import annotations

from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from app.application.dtos.tool_dto import ToolContext
from app.application.tools.registry import ToolRegistry
from app.core.exceptions import ToolExecutionError


async def run_tool(
    registry: ToolRegistry, name: str, arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    try:
        return await registry.execute(name, arguments, context)
    except ToolExecutionError as exc:
        raise ToolError(exc.message) from exc
