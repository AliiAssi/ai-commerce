from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from app.application.dtos.product_dto import (
    CategoryDTO,
    ProductCreateDTO,
    ProductDTO,
    ProductListDTO,
    ProductSearchParams,
    ProductStockDTO,
    ProductUpdateDTO,
)


class IProductRepository(ABC):
    @abstractmethod
    async def search(self, params: ProductSearchParams) -> ProductListDTO: ...

    @abstractmethod
    async def get(self, product_id: int) -> ProductDTO | None: ...

    # Preserves the given order — it is a ranking, not a set.
    @abstractmethod
    async def list_by_ids(self, product_ids: list[int]) -> list[ProductDTO]: ...

    # Used for seed idempotency and duplicate checks.
    @abstractmethod
    async def find_by_name(self, name: str) -> ProductDTO | None: ...

    @abstractmethod
    async def create(self, data: ProductCreateDTO) -> ProductDTO: ...

    @abstractmethod
    async def update(self, product_id: int, data: ProductUpdateDTO) -> ProductDTO | None: ...

    @abstractmethod
    async def set_archived(self, product_id: int, archived: bool) -> ProductDTO | None: ...

    # Ordered, FOR UPDATE — for stock mutations that must not deadlock against each other.
    @abstractmethod
    async def lock_products(self, product_ids: list[int]) -> list[ProductStockDTO]: ...

    # Caller must hold the row lock from lock_products first.
    @abstractmethod
    async def apply_stock_delta(self, product_id: int, delta: int) -> None: ...

    @abstractmethod
    async def update_rating(
        self, product_id: int, rating_avg: Decimal, review_count: int
    ) -> None: ...

    @abstractmethod
    async def product_counts(self) -> tuple[int, int]: ...

    @abstractmethod
    async def low_stock(self, threshold: int, limit: int) -> list[ProductDTO]: ...

    @abstractmethod
    async def list_categories(self) -> list[CategoryDTO]: ...

    @abstractmethod
    async def get_category(self, category_id: int) -> CategoryDTO | None: ...

    @abstractmethod
    async def get_category_by_slug(self, slug: str) -> CategoryDTO | None: ...

    @abstractmethod
    async def create_category(self, name: str, slug: str) -> CategoryDTO: ...
