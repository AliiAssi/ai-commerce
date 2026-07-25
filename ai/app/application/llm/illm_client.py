from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.application.llm.llm_dtos import LLMMessageDTO, LLMReplyDTO, LLMStreamEventDTO


class ILLMClient(ABC):
    @abstractmethod
    async def chat(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> LLMReplyDTO: ...

    @abstractmethod
    def stream(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMStreamEventDTO]: ...
