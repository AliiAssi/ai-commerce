from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str  # snake_case verb an LLM would guess, e.g. "search_products"
    description: str  # LLM-facing prose, part of the prompt
    params_model: type[BaseModel]
    customer_scoped: bool = False


@dataclass(frozen=True)
class ToolContext:
    source: Literal["chat", "mcp"]
    user_email: str | None = None


class EmptyParams(BaseModel):
    """No arguments."""
