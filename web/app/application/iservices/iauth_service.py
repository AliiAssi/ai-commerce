from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.user_dto import TokenDTO, UserDTO


class IAuthService(ABC):
    @abstractmethod
    async def register(self, email: str, password: str) -> TokenDTO: ...

    @abstractmethod
    async def login(self, email: str, password: str) -> TokenDTO: ...

    @abstractmethod
    async def get_me(self, user_id: int) -> UserDTO: ...
