from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.dtos.order_dto import OrderItemCreateDTO, OrderStatus
from app.application.dtos.product_dto import ProductCreateDTO
from app.application.services.admin_service import AdminService
from app.application.services.product_service import ProductService
from app.core.authz import Permission, has_permission
from app.core.config import Settings
from tests.unit.fakes import (
    FakeAuditLogRepository,
    FakeOrderRepository,
    FakeProductRepository,
    FakeUserRepository,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://unused/unused",
        JWT_SECRET="unit-test-secret-0123456789abcdef",
        LOW_STOCK_THRESHOLD=5,
    )


def test_role_permission_map():
    assert has_permission("admin", Permission.ADMIN_ACCESS)
    assert has_permission("admin", Permission.PRODUCTS_MANAGE)
    assert not has_permission("customer", Permission.ADMIN_ACCESS)
    assert not has_permission("unknown-role", Permission.ORDERS_MANAGE)


async def test_dashboard_stats(settings):
    products = FakeProductRepository()
    orders = FakeOrderRepository()
    users = FakeUserRepository()
    audit = FakeAuditLogRepository()
    service = AdminService(products, orders, users, audit, settings)

    healthy = products.seed("Healthy", stock=50)
    low = products.seed("Low", stock=2)
    archived = products.seed("Old", archived=True)
    await users.create("a@x.test", "h", "customer")
    await users.create("admin@x.test", "h", "admin")

    item = OrderItemCreateDTO(
        product_id=healthy.id, product_name="Healthy", unit_price=Decimal("10.00"), quantity=1
    )
    await orders.create(1, [item], Decimal("10.00"))
    await orders.create(1, [item], Decimal("10.00"), OrderStatus.CANCELLED)

    stats = await service.dashboard()

    assert stats.revenue == Decimal("10.00")
    assert stats.orders_total == 2
    assert stats.orders_by_status == {"paid": 1, "cancelled": 1}
    assert stats.product_count == 3
    assert stats.active_product_count == 2
    assert stats.customer_count == 1
    assert [p.id for p in stats.low_stock] == [low.id]
    assert archived.id not in [p.id for p in stats.low_stock]


async def test_product_admin_actions_are_audited():
    products = FakeProductRepository()
    audit = FakeAuditLogRepository()
    service = ProductService(products, audit)
    category = await products.create_category("General", "general")

    created = await service.admin_create(
        7,
        ProductCreateDTO(
            name="Widget",
            description="A widget",
            price=Decimal("9.99"),
            stock=3,
            category_id=category.id,
        ),
    )
    await service.admin_adjust_stock(7, created.id, 5)
    await service.admin_set_archived(7, created.id, True)

    actions = [e.action for e in audit.entries]
    assert actions == ["product_create", "stock_adjust", "product_archive"]
    assert audit.entries[1].detail == {"delta": 5, "stock_after": 8}
    assert all(e.admin_id == 7 for e in audit.entries)
