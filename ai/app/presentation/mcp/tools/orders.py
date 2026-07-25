from __future__ import annotations

from typing import Any

from app.application.dtos.tool_dto import ToolContext
from app.application.tools.registry import ToolRegistry
from app.presentation.mcp.tools.common import run_tool


def register(mcp, registry: ToolRegistry) -> None:
    async def get_order(order_id: int, user_email: str | None = None) -> dict[str, Any]:
        return await run_tool(
            registry,
            "get_order",
            {"order_id": order_id, "user_email": user_email},
            ToolContext(source="mcp", user_email=user_email),
        )

    async def list_orders(user_email: str | None = None, limit: int = 10) -> dict[str, Any]:
        return await run_tool(
            registry,
            "list_orders",
            {"user_email": user_email, "limit": limit},
            ToolContext(source="mcp", user_email=user_email),
        )

    async def get_order_status(order_id: int, user_email: str | None = None) -> dict[str, Any]:
        return await run_tool(
            registry,
            "get_order_status",
            {"order_id": order_id, "user_email": user_email},
            ToolContext(source="mcp", user_email=user_email),
        )

    for fn in (get_order, list_orders, get_order_status):
        spec = registry.spec(fn.__name__)
        mcp.add_tool(fn, name=spec.name, description=spec.description)
