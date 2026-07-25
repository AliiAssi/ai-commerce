from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.ai_dto import ChatStreamHandle


class IAIGateway(ABC):
    @abstractmethod
    async def open_chat(
        self, message: str, session_id: str | None, user_email: str | None
    ) -> ChatStreamHandle: ...

    @abstractmethod
    async def aclose(self) -> None: ...
