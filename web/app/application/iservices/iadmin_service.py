from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.admin_dto import AdminStatsDTO
from app.application.dtos.audit_dto import AuditPageDTO
from app.application.dtos.order_dto import AdminOrderPageDTO, OrderSearchParams


class IAdminService(ABC):
    @abstractmethod
    async def dashboard(self) -> AdminStatsDTO: ...

    @abstractmethod
    async def list_orders(self, params: OrderSearchParams) -> AdminOrderPageDTO: ...

    @abstractmethod
    async def order_status_counts(self) -> dict[str, int]: ...

    @abstractmethod
    async def audit_page(self, page: int, page_size: int) -> AuditPageDTO: ...
