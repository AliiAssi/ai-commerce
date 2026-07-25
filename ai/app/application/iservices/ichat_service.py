from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.application.dtos.chat_dto import ChatSessionDTO, ChatStreamEventDTO


class IChatService(ABC):
    # mint a new session or return the existing one; raises SessionNotFoundError on a bad id
    @abstractmethod
    async def resolve_session(
        self, session_id: uuid.UUID | None, user_email: str | None
    ) -> ChatSessionDTO: ...

    # run the agent loop for one user message, streaming token/tool/done/error events
    @abstractmethod
    def stream_reply(
        self, session: ChatSessionDTO, message: str
    ) -> AsyncIterator[ChatStreamEventDTO]: ...
