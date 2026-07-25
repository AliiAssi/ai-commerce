from __future__ import annotations

from abc import ABC, abstractmethod

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
    async def get(self, product_id: int) -> ProductReadDTO | None: ...

    @abstractmethod
    async def list_categories(self) -> list[CategoryReadDTO]: ...

    @abstractmethod
    async def top_rated(self, limit: int) -> list[ProductReadDTO]: ...

    @abstractmethod
    async def low_stock(self, limit: int) -> list[ProductReadDTO]: ...

    @abstractmethod
    async def stats(self) -> StoreStatsDTO: ...
