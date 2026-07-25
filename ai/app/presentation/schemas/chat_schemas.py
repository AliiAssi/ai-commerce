from __future__ import annotations

import json
import uuid

from pydantic import BaseModel, Field

from app.application.dtos.chat_dto import ChatStreamEventDTO


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: uuid.UUID | None = None
    user_email: str | None = None


def format_sse(event: ChatStreamEventDTO) -> str:
    payload: dict[str, object] = {"type": event.type}
    if event.type == "token":
        payload["text"] = event.text or ""
    elif event.type == "tool":
        payload["name"] = event.name
    elif event.type == "done":
        payload["session_id"] = str(event.session_id) if event.session_id else None
    elif event.type == "error":
        payload["message"] = event.message or ""
    return f"data: {json.dumps(payload)}\n\n"
