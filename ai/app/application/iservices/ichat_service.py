from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.application.dtos.chat_dto import ChatSessionDTO, ChatStreamEventDTO


class IChatService(ABC):
    @abstractmethod
    async def resolve_session(
        self, session_id: uuid.UUID | None, user_email: str | None
    ) -> ChatSessionDTO: ...

    @abstractmethod
    def stream_reply(
        self, session: ChatSessionDTO, message: str
    ) -> AsyncIterator[ChatStreamEventDTO]: ...
