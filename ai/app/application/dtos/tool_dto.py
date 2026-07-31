from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params_model: type[BaseModel]
    customer_scoped: bool = False
    opens_own_scope: bool = False


@dataclass(frozen=True)
class ToolContext:
    source: Literal["chat", "mcp"]
    user_email: str | None = None


class EmptyParams(BaseModel): ...
