from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.ai_dto import ChatStreamHandle, RemoteSearchResult
from app.application.dtos.product_dto import ProductSearchParams


class IAIGateway(ABC):
    @abstractmethod
    async def open_chat(
        self, message: str, session_id: str | None, user_email: str | None
    ) -> ChatStreamHandle: ...

    # Returns None when the AI service could not answer for any reason — unreachable, slow,
    # erroring, or returning something that does not parse. The caller's job is then to serve
    # the lexical fallback, so this never raises and never leaks a provider error (§12).
    @abstractmethod
    async def search(self, params: ProductSearchParams) -> RemoteSearchResult | None: ...

    @abstractmethod
    async def warm(self) -> None: ...

    @abstractmethod
    async def aclose(self) -> None: ...
