from __future__ import annotations

from app.application.dtos.admin_dto import AdminStatsDTO
from app.application.dtos.audit_dto import AuditPageDTO
from app.application.dtos.order_dto import AdminOrderPageDTO, OrderSearchParams
from app.application.iservices.iadmin_service import IAdminService
from app.core.config import Settings
from app.infrastructure.irepositories.iaudit_log_repository import IAuditLogRepository
from app.infrastructure.irepositories.iorder_repository import IOrderRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository
from app.infrastructure.irepositories.iuser_repository import IUserRepository


class AdminService(IAdminService):
    def __init__(
        self,
        products: IProductRepository,
        orders: IOrderRepository,
        users: IUserRepository,
        audit: IAuditLogRepository,
        settings: Settings,
    ) -> None:
        self._products = products
        self._orders = orders
        self._users = users
        self._audit = audit
        self._settings = settings

    async def dashboard(self) -> AdminStatsDTO:
        product_count, active_product_count = await self._products.product_counts()
        orders_by_status = await self._orders.counts_by_status()
        recent = await self._orders.search_all(OrderSearchParams(page=1, page_size=6))
        return AdminStatsDTO(
            revenue=await self._orders.revenue_total(),
            orders_by_status=orders_by_status,
            orders_total=sum(orders_by_status.values()),
            product_count=product_count,
            active_product_count=active_product_count,
            customer_count=await self._users.customer_count(),
            low_stock=await self._products.low_stock(self._settings.LOW_STOCK_THRESHOLD, 5),
            recent_orders=recent.items,
            recent_activity=await self._audit.recent(6),
        )

    async def list_orders(self, params: OrderSearchParams) -> AdminOrderPageDTO:
        return await self._orders.search_all(params)

    async def order_status_counts(self) -> dict[str, int]:
        return await self._orders.counts_by_status()

    async def audit_page(self, page: int, page_size: int) -> AuditPageDTO:
        return await self._audit.list(page, page_size)
