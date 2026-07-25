from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.chat_dto import ChatMessageDTO, ChatSessionDTO
from app.infrastructure.irepositories.ichat_repository import IChatRepository
from app.infrastructure.models.chat_message import ChatMessage
from app.infrastructure.models.chat_session import ChatSession


class ChatRepository(IChatRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(self, user_email: str | None) -> ChatSessionDTO:
        row = ChatSession(user_email=user_email)
        self._session.add(row)
        await self._session.flush()
        return ChatSessionDTO(id=row.id, user_email=row.user_email)

    async def get_session(self, session_id: uuid.UUID) -> ChatSessionDTO | None:
        row = await self._session.get(ChatSession, session_id)
        return None if row is None else ChatSessionDTO(id=row.id, user_email=row.user_email)

    async def list_messages(self, session_id: uuid.UUID) -> list[ChatMessageDTO]:
        stmt = (
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            ChatMessageDTO(role=r.role, content=r.content, tool_calls=r.tool_calls) for r in rows
        ]

    async def count_messages(self, session_id: uuid.UUID) -> int:
        stmt = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
        return await self._session.scalar(stmt) or 0

    async def append_messages(self, session_id: uuid.UUID, messages: list[ChatMessageDTO]) -> None:
        self._session.add_all(
            [
                ChatMessage(
                    session_id=session_id,
                    role=m.role,
                    content=m.content,
                    tool_calls=m.tool_calls,
                )
                for m in messages
            ]
        )
        await self._session.execute(
            update(ChatSession).where(ChatSession.id == session_id).values(updated_at=func.now())
        )
        await self._session.flush()
