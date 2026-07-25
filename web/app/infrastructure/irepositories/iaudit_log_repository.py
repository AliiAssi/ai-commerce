from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.application.dtos.audit_dto import AuditLogDTO, AuditPageDTO


class IAuditLogRepository(ABC):
    @abstractmethod
    async def add(
        self,
        admin_id: int,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None: ...

    @abstractmethod
    async def list(self, page: int, page_size: int) -> AuditPageDTO: ...

    @abstractmethod
    async def recent(self, limit: int) -> list[AuditLogDTO]: ...
