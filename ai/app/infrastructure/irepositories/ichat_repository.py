from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.application.dtos.chat_dto import ChatMessageDTO, ChatSessionDTO


class IChatRepository(ABC):
    @abstractmethod
    async def create_session(self, user_email: str | None) -> ChatSessionDTO: ...

    @abstractmethod
    async def get_session(self, session_id: uuid.UUID) -> ChatSessionDTO | None: ...

    @abstractmethod
    async def list_messages(self, session_id: uuid.UUID) -> list[ChatMessageDTO]: ...

    @abstractmethod
    async def count_messages(self, session_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def append_messages(
        self, session_id: uuid.UUID, messages: list[ChatMessageDTO]
    ) -> None: ...
