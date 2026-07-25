from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class LLMMessageDTO:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[LLMToolCallDTO] = field(default_factory=list)
    tool_name: str | None = None  # set on role="tool" results


@dataclass
class LLMToolCallDTO:
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMUsageDTO:
    prompt_tokens: int
    completion_tokens: int
    duration_ms: float


@dataclass
class LLMReplyDTO:
    content: str
    tool_calls: list[LLMToolCallDTO] = field(default_factory=list)
    usage: LLMUsageDTO | None = None


@dataclass
class LLMStreamEventDTO:
    type: Literal["token", "tool_call", "done"]
    text: str | None = None  # token events
    tool_call: LLMToolCallDTO | None = None  # tool_call events
    usage: LLMUsageDTO | None = None  # done events
