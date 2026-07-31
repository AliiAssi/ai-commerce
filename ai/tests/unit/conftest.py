from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.application.tools.bootstrap import build_tool_registry
from app.application.tools.registry import ToolRegistry
from app.infrastructure.irepositories.iorder_read_repository import IOrderReadRepository
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository
from app.infrastructure.irepositories.ireview_read_repository import IReviewReadRepository
from tests.unit.fakes import (
    FakeOrderReadRepository,
    FakeProductReadRepository,
    FakeReviewReadRepository,
)


class FakeScope:
    def __init__(self, bindings: dict[type, Any]) -> None:
        self._bindings = bindings

    def resolve(self, interface: type) -> Any:
        return self._bindings[interface]


def build_fake_registry(
    products: FakeProductReadRepository | None = None,
    orders: FakeOrderReadRepository | None = None,
    reviews: FakeReviewReadRepository | None = None,
) -> ToolRegistry:
    bindings = {
        IProductReadRepository: products or FakeProductReadRepository(),
        IOrderReadRepository: orders or FakeOrderReadRepository(),
        IReviewReadRepository: reviews or FakeReviewReadRepository(),
    }
    scope = FakeScope(bindings)

    @asynccontextmanager
    async def scope_factory() -> AsyncIterator[FakeScope]:
        yield scope

    return build_tool_registry(scope_factory=scope_factory)
