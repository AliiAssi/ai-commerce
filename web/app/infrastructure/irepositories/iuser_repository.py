from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.user_dto import UserCredentialsDTO, UserDTO


class IUserRepository(ABC):
    @abstractmethod
    async def get(self, user_id: int) -> UserDTO | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> UserDTO | None: ...

    @abstractmethod
    async def get_credentials(self, email: str) -> UserCredentialsDTO | None: ...

    @abstractmethod
    async def create(self, email: str, password_hash: str, role: str) -> UserDTO: ...

    @abstractmethod
    async def customer_count(self) -> int: ...
