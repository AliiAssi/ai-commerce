from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.services.cart_service import CartService
from app.core.exceptions import NotFoundError, OutOfStockError
from tests.unit.fakes import FakeCartRepository, FakeProductRepository


@pytest.fixture
def products() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def service(products: FakeProductRepository) -> CartService:
    return CartService(FakeCartRepository(products), products)


async def test_add_item_computes_totals(service: CartService, products: FakeProductRepository):
    p = products.seed("Widget", price="9.99", stock=5)
    cart = await service.add_item(user_id=1, product_id=p.id, quantity=2)
    assert cart.total_quantity == 2
    assert cart.grand_total == Decimal("19.98")
    assert cart.items[0].line_total == Decimal("19.98")


async def test_add_item_accumulates_and_respects_stock(
    service: CartService, products: FakeProductRepository
):
    p = products.seed("Widget", stock=5)
    await service.add_item(1, p.id, 3)
    with pytest.raises(OutOfStockError):
        await service.add_item(1, p.id, 3)
    cart = await service.add_item(1, p.id, 2)
    assert cart.total_quantity == 5


async def test_add_unknown_or_archived_product_404(
    service: CartService, products: FakeProductRepository
):
    archived = products.seed("Old", archived=True)
    with pytest.raises(NotFoundError):
        await service.add_item(1, archived.id, 1)
    with pytest.raises(NotFoundError):
        await service.add_item(1, 999, 1)


async def test_add_out_of_stock_product_conflicts(
    service: CartService, products: FakeProductRepository
):
    p = products.seed("Gone", stock=0)
    with pytest.raises(OutOfStockError):
        await service.add_item(1, p.id, 1)


async def test_update_item_sets_exact_quantity(
    service: CartService, products: FakeProductRepository
):
    p = products.seed("Widget", stock=10)
    await service.add_item(1, p.id, 2)
    cart = await service.update_item(1, p.id, 7)
    assert cart.items[0].quantity == 7
    with pytest.raises(OutOfStockError):
        await service.update_item(1, p.id, 11)


async def test_update_missing_item_404(service: CartService, products: FakeProductRepository):
    p = products.seed("Widget")
    with pytest.raises(NotFoundError):
        await service.update_item(1, p.id, 1)


async def test_remove_item(service: CartService, products: FakeProductRepository):
    p = products.seed("Widget")
    await service.add_item(1, p.id, 1)
    cart = await service.remove_item(1, p.id)
    assert cart.items == []
    with pytest.raises(NotFoundError):
        await service.remove_item(1, p.id)
