from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.audit_dto import AuditLogDTO, AuditPageDTO
from app.infrastructure.irepositories.iaudit_log_repository import IAuditLogRepository
from app.infrastructure.models.audit import AuditLog


class AuditLogRepository(IAuditLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_dto(entry: AuditLog) -> AuditLogDTO:
        return AuditLogDTO(
            id=entry.id,
            admin_id=entry.admin_id,
            admin_email=entry.admin.email,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            detail=entry.detail,
            created_at=entry.created_at,
        )

    async def add(
        self,
        admin_id: int,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditLog(
                admin_id=admin_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                detail=detail,
            )
        )
        await self._session.flush()

    async def list(self, page: int, page_size: int) -> AuditPageDTO:
        total = await self._session.scalar(select(func.count(AuditLog.id))) or 0
        entries = (
            await self._session.scalars(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return AuditPageDTO(
            items=[self._to_dto(e) for e in entries], total=total, page=page, page_size=page_size
        )

    async def recent(self, limit: int) -> list[AuditLogDTO]:
        entries = (
            await self._session.scalars(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(limit)
            )
        ).all()
        return [self._to_dto(e) for e in entries]
