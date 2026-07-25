from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.user_dto import UserCredentialsDTO, UserDTO
from app.infrastructure.irepositories.iuser_repository import IUserRepository
from app.infrastructure.models.user import User


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_dto(user: User) -> UserDTO:
        return UserDTO(id=user.id, email=user.email, role=user.role, created_at=user.created_at)

    async def get(self, user_id: int) -> UserDTO | None:
        user = await self._session.get(User, user_id)
        return self._to_dto(user) if user else None

    async def get_by_email(self, email: str) -> UserDTO | None:
        user = await self._session.scalar(select(User).where(User.email == email))
        return self._to_dto(user) if user else None

    async def get_credentials(self, email: str) -> UserCredentialsDTO | None:
        user = await self._session.scalar(select(User).where(User.email == email))
        if user is None:
            return None
        return UserCredentialsDTO(
            id=user.id,
            email=user.email,
            role=user.role,
            password_hash=user.password_hash,
            created_at=user.created_at,
        )

    async def create(self, email: str, password_hash: str, role: str) -> UserDTO:
        user = User(email=email, password_hash=password_hash, role=role)
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return self._to_dto(user)

    async def customer_count(self) -> int:
        return (
            await self._session.scalar(select(func.count(User.id)).where(User.role == "customer"))
        ) or 0
