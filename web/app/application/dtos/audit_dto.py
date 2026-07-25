from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogDTO(BaseModel):
    id: int
    admin_id: int
    admin_email: str
    action: str
    entity_type: str
    entity_id: int | None
    detail: dict[str, Any] | None
    created_at: datetime


class AuditPageDTO(BaseModel):
    items: list[AuditLogDTO]
    total: int
    page: int
    page_size: int
