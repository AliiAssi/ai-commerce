from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.dtos.search_params import ProductSearchParams
from tests.unit.fakes import (
    FakeOrderReadRepository,
    FakeProductReadRepository,
    FakeReviewReadRepository,
)


@pytest.fixture
def products() -> FakeProductReadRepository:
    repo = FakeProductReadRepository()
    repo.seed("Alpha Tent", price="100.00", stock=5, rating_avg="4.50", review_count=8)
    repo.seed("Beta Stove", price="25.00", stock=0, rating_avg="4.90", review_count=3)
    repo.seed("Gamma Lantern", price="15.00", stock=12, category="Light", category_slug="light")
    return repo


async def test_search_filters_and_sorts(products: FakeProductReadRepository) -> None:
    page = await products.search(ProductSearchParams(in_stock_only=True, sort="price_asc"))
    assert [p.name for p in page.items] == ["Gamma Lantern", "Alpha Tent"]
    assert page.total == 2


async def test_search_by_category_and_price(products: FakeProductReadRepository) -> None:
    page = await products.search(ProductSearchParams(category_slug="gear", max_price=50))
    assert [p.name for p in page.items] == ["Beta Stove"]


async def test_stats_and_categories(products: FakeProductReadRepository) -> None:
    stats = await products.stats()
    assert stats.product_count == 3
    assert stats.category_count == 2
    assert stats.price_min == Decimal("15.00")
    assert stats.price_max == Decimal("100.00")


async def test_order_scoping_hides_other_customers() -> None:
    orders = FakeOrderReadRepository()
    mine = orders.seed("me@test.com")
    orders.seed("someone@test.com")

    assert (await orders.get(mine.id, user_email="me@test.com")) is not None
    assert (await orders.get(mine.id, user_email="other@test.com")) is None
    assert len(await orders.list_for_user("me@test.com", 10)) == 1


async def test_reviews_scoped_to_product() -> None:
    reviews = FakeReviewReadRepository()
    reviews.seed(1, rating=4, text="ok")
    assert len(await reviews.list_for_product(1, 10)) == 1
    assert await reviews.list_for_product(2, 10) == []
