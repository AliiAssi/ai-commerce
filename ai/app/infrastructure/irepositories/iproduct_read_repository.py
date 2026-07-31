from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.application.dtos.search_params import ProductSearchParams
from app.application.dtos.store_read_dto import (
    CategoryReadDTO,
    ProductPageDTO,
    ProductReadDTO,
    StoreStatsDTO,
)


class IProductReadRepository(ABC):
    @abstractmethod
    async def search(self, params: ProductSearchParams) -> ProductPageDTO: ...

    @abstractmethod
    async def by_ids(self, product_ids: Sequence[int]) -> list[ProductReadDTO]:
        """Load these products, in the order given, skipping any that are gone."""

    @abstractmethod
    async def get(self, product_id: int) -> ProductReadDTO | None: ...

    @abstractmethod
    async def list_categories(self) -> list[CategoryReadDTO]: ...

    @abstractmethod
    async def top_rated(self, limit: int) -> list[ProductReadDTO]: ...

    @abstractmethod
    async def low_stock(self, limit: int) -> list[ProductReadDTO]: ...

    @abstractmethod
    async def stats(self) -> StoreStatsDTO: ...
