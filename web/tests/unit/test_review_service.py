from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.dtos.order_dto import OrderItemCreateDTO
from app.application.dtos.review_dto import ReviewIneligibility
from app.application.events.bus import EventBus
from app.application.services.review_service import ReviewService
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from tests.unit.fakes import (
    FakeOrderRepository,
    FakeProductRepository,
    FakeReviewRepository,
    FakeUserRepository,
)


@pytest.fixture
def products() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def orders() -> FakeOrderRepository:
    return FakeOrderRepository()


@pytest.fixture
def users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def service(products, orders, users) -> ReviewService:
    return ReviewService(FakeReviewRepository(users), orders, products, EventBus())


# a delivered order makes the user a verified purchaser
async def _purchase(orders: FakeOrderRepository, user_id: int, product) -> None:
    item = OrderItemCreateDTO(
        product_id=product.id, product_name=product.name, unit_price=product.price, quantity=1
    )
    await orders.create(user_id, [item], product.price)


async def test_non_purchaser_cannot_review(service, products, users):
    user = await users.create("a@x.test", "h", "customer")
    p = products.seed("Widget")
    with pytest.raises(ForbiddenError):
        await service.create(user.id, p.id, 5, "great product")


async def test_purchaser_review_updates_product_rating(service, products, orders, users):
    user = await users.create("a@x.test", "h", "customer")
    p = products.seed("Widget")
    await _purchase(orders, user.id, p)

    review = await service.create(user.id, p.id, 4, "solid, does the job")

    assert review.rating == 4
    updated = await products.get(p.id)
    assert updated.rating_avg == Decimal("4.00")
    assert updated.review_count == 1


async def test_duplicate_review_conflicts(service, products, orders, users):
    user = await users.create("a@x.test", "h", "customer")
    p = products.seed("Widget")
    await _purchase(orders, user.id, p)
    await service.create(user.id, p.id, 4, "solid, does the job")

    with pytest.raises(ConflictError):
        await service.create(user.id, p.id, 5, "changed my mind")


async def test_review_unknown_product_404(service, users):
    user = await users.create("a@x.test", "h", "customer")
    with pytest.raises(NotFoundError):
        await service.create(user.id, 999, 5, "ghost product")


async def test_average_over_multiple_reviewers(service, products, orders, users):
    p = products.seed("Widget")
    u1 = await users.create("a@x.test", "h", "customer")
    u2 = await users.create("b@x.test", "h", "customer")
    await _purchase(orders, u1.id, p)
    await _purchase(orders, u2.id, p)

    await service.create(u1.id, p.id, 5, "love it")
    await service.create(u2.id, p.id, 2, "meh at best")

    updated = await products.get(p.id)
    assert updated.rating_avg == Decimal("3.50")
    assert updated.review_count == 2


async def test_eligibility_reports_a_signed_out_caller_without_a_401(service, products):
    p = products.seed("Widget")
    result = await service.eligibility(None, p.id)
    assert result.can_review is False
    assert result.reason is ReviewIneligibility.NOT_AUTHENTICATED
    assert result.review is None


async def test_eligibility_refuses_a_signed_in_non_purchaser(service, products, users):
    user = await users.create("a@x.test", "h", "customer")
    p = products.seed("Widget")
    result = await service.eligibility(user.id, p.id)
    assert result.can_review is False
    assert result.reason is ReviewIneligibility.NOT_PURCHASED


async def test_eligibility_admits_a_purchaser_who_has_not_reviewed(
    service, products, orders, users
):
    user = await users.create("a@x.test", "h", "customer")
    p = products.seed("Widget")
    await _purchase(orders, user.id, p)

    result = await service.eligibility(user.id, p.id)
    assert result.can_review is True
    assert result.reason is None


async def test_eligibility_returns_the_review_the_caller_already_wrote(
    service, products, orders, users
):
    user = await users.create("a@x.test", "h", "customer")
    p = products.seed("Widget")
    await _purchase(orders, user.id, p)
    created = await service.create(user.id, p.id, 5, "Excellent.")

    result = await service.eligibility(user.id, p.id)
    assert result.can_review is False
    assert result.reason is ReviewIneligibility.ALREADY_REVIEWED
    assert result.review is not None
    assert result.review.id == created.id
    assert result.review.rating == 5


async def test_eligibility_matches_what_create_would_do(service, products, orders, users):
    """The endpoint exists to predict `create`; a disagreement is the bug it must not have."""
    user = await users.create("a@x.test", "h", "customer")
    p = products.seed("Widget")

    assert (await service.eligibility(user.id, p.id)).can_review is False
    with pytest.raises(ForbiddenError):
        await service.create(user.id, p.id, 4, "Nice one.")

    await _purchase(orders, user.id, p)
    assert (await service.eligibility(user.id, p.id)).can_review is True
    await service.create(user.id, p.id, 4, "Nice one.")

    assert (await service.eligibility(user.id, p.id)).can_review is False
    with pytest.raises(ConflictError):
        await service.create(user.id, p.id, 4, "Again.")


async def test_eligibility_404s_on_an_unknown_product(service):
    with pytest.raises(NotFoundError):
        await service.eligibility(None, 999)


async def test_eligibility_404s_on_an_archived_product(service, products):
    p = products.seed("Gone", archived=True)
    with pytest.raises(NotFoundError):
        await service.eligibility(None, p.id)
