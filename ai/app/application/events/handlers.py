from __future__ import annotations

import logging

from app.application.events.bus import EventBus
from app.application.events.definitions import ChatTurnCompleted, ToolExecuted

logger = logging.getLogger(__name__)


def register_handlers(bus: EventBus) -> None:
    bus.subscribe(ToolExecuted, _on_tool_executed)
    bus.subscribe(ChatTurnCompleted, _on_chat_turn_completed)


def _on_tool_executed(event: ToolExecuted) -> None:
    logger.info(
        "event tool_executed name=%s source=%s duration_ms=%.0f ok=%s",
        event.name,
        event.source,
        event.duration_ms,
        event.ok,
    )


def _on_chat_turn_completed(event: ChatTurnCompleted) -> None:
    logger.info(
        "event chat_turn_completed session_id=%s tool_calls=%s prompt_tokens=%s "
        "completion_tokens=%s",
        event.session_id,
        event.tool_calls,
        event.prompt_tokens,
        event.completion_tokens,
    )
