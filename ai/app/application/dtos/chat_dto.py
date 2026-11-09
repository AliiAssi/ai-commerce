from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel

from app.application.dtos.reference_dto import MoreResultsDTO, ProductCardDTO

ChatEventType = Literal["token", "tool", "products", "done", "error"]


class ChatMessageDTO(BaseModel):
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None


class ChatSessionDTO(BaseModel):
    id: uuid.UUID
    user_email: str | None


class ChatStreamEventDTO(BaseModel):
    type: ChatEventType
    text: str | None = None
    name: str | None = None
    session_id: uuid.UUID | None = None
    message: str | None = None
    products: list[ProductCardDTO] | None = None
    more: MoreResultsDTO | None = None
