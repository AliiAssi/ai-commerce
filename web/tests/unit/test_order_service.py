from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.dtos.order_dto import OrderStatus
from app.application.events.bus import EventBus
from app.application.services.cart_service import CartService
from app.application.services.order_service import OrderService
from app.core.exceptions import ConflictError, NotFoundError, OutOfStockError
from tests.unit.fakes import (
    FakeAuditLogRepository,
    FakeCartRepository,
    FakeOrderRepository,
    FakeProductRepository,
)


@pytest.fixture
def products() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def carts(products: FakeProductRepository) -> FakeCartRepository:
    return FakeCartRepository(products)


@pytest.fixture
def orders() -> FakeOrderRepository:
    return FakeOrderRepository()


@pytest.fixture
def audit() -> FakeAuditLogRepository:
    return FakeAuditLogRepository()


@pytest.fixture
def service(
    orders: FakeOrderRepository,
    carts: FakeCartRepository,
    products: FakeProductRepository,
    audit: FakeAuditLogRepository,
) -> OrderService:
    return OrderService(orders, carts, products, EventBus(), audit)


@pytest.fixture
def cart_service(carts: FakeCartRepository, products: FakeProductRepository) -> CartService:
    return CartService(carts, products)


async def test_checkout_happy_path(service, cart_service, products):
    a = products.seed("A", price="10.00", stock=5)
    b = products.seed("B", price="3.50", stock=2)
    await cart_service.add_item(1, a.id, 2)
    await cart_service.add_item(1, b.id, 1)

    order = await service.checkout(1)

    assert order.status == OrderStatus.PAID
    assert order.total == Decimal("23.50")
    assert {(i.product_id, i.quantity) for i in order.items} == {(a.id, 2), (b.id, 1)}
    assert (await products.get(a.id)).stock == 3
    assert (await products.get(b.id)).stock == 1
    assert (await cart_service.get_cart(1)).items == []


async def test_checkout_snapshots_price_at_purchase(service, cart_service, products):
    a = products.seed("A", price="10.00", stock=5)
    await cart_service.add_item(1, a.id, 1)
    order = await service.checkout(1)
    assert order.items[0].unit_price == Decimal("10.00")


async def test_checkout_empty_cart_conflicts(service, cart_service):
    await cart_service.get_cart(1)
    with pytest.raises(ConflictError):
        await service.checkout(1)


async def test_checkout_insufficient_stock_fails_whole_order(service, cart_service, products):
    a = products.seed("A", stock=5)
    b = products.seed("B", stock=5)
    await cart_service.add_item(1, a.id, 2)
    await cart_service.add_item(1, b.id, 2)
    await products.apply_stock_delta(b.id, -4)

    with pytest.raises(OutOfStockError) as exc:
        await service.checkout(1)

    assert any(o["product_id"] == b.id for o in exc.value.details)
    assert (await products.get(a.id)).stock == 5


async def test_cancel_restores_stock(service, cart_service, products):
    a = products.seed("A", stock=5)
    await cart_service.add_item(1, a.id, 3)
    order = await service.checkout(1)
    assert (await products.get(a.id)).stock == 2

    cancelled = await service.cancel(1, order.id)

    assert cancelled.status == OrderStatus.CANCELLED
    assert (await products.get(a.id)).stock == 5


async def test_cancel_after_ship_conflicts(service, cart_service, products, orders):
    a = products.seed("A", stock=5)
    await cart_service.add_item(1, a.id, 1)
    order = await service.checkout(1)
    await orders.set_status(order.id, OrderStatus.SHIPPED)

    with pytest.raises(ConflictError):
        await service.cancel(1, order.id)


async def test_get_order_hides_other_users_orders(service, cart_service, products):
    a = products.seed("A", stock=5)
    await cart_service.add_item(1, a.id, 1)
    order = await service.checkout(1)

    with pytest.raises(NotFoundError):
        await service.get_order(2, order.id)


async def test_admin_advance_walks_the_lifecycle(service, cart_service, products, audit):
    a = products.seed("A", stock=5)
    await cart_service.add_item(1, a.id, 1)
    order = await service.checkout(1)

    shipped = await service.admin_advance_status(99, order.id)
    assert shipped.status == OrderStatus.SHIPPED
    delivered = await service.admin_advance_status(99, order.id)
    assert delivered.status == OrderStatus.DELIVERED
    with pytest.raises(ConflictError):
        await service.admin_advance_status(99, order.id)

    assert [e.action for e in audit.entries] == ["order_status_advance", "order_status_advance"]
    assert audit.entries[0].detail == {"from": "paid", "to": "shipped"}


async def test_admin_advance_rejects_cancelled(service, cart_service, products):
    a = products.seed("A", stock=5)
    await cart_service.add_item(1, a.id, 1)
    order = await service.checkout(1)
    await service.cancel(1, order.id)

    with pytest.raises(ConflictError):
        await service.admin_advance_status(99, order.id)
