from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolExecuted:
    name: str
    source: str
    duration_ms: float
    ok: bool


@dataclass(frozen=True)
class ChatTurnCompleted:
    session_id: str
    tool_calls: int
    prompt_tokens: int
    completion_tokens: int
