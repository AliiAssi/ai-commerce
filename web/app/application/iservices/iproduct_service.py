from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.product_dto import (
    CategoryDTO,
    ProductCreateDTO,
    ProductDTO,
    ProductListDTO,
    ProductSearchParams,
    ProductUpdateDTO,
)


class IProductService(ABC):
    @abstractmethod
    async def search(self, params: ProductSearchParams) -> ProductListDTO: ...

    # Archived products 404.
    @abstractmethod
    async def get(self, product_id: int) -> ProductDTO: ...

    @abstractmethod
    async def admin_get(self, product_id: int) -> ProductDTO: ...

    @abstractmethod
    async def list_categories(self) -> list[CategoryDTO]: ...

    @abstractmethod
    async def admin_create(self, admin_id: int, data: ProductCreateDTO) -> ProductDTO: ...

    @abstractmethod
    async def admin_update(
        self, admin_id: int, product_id: int, data: ProductUpdateDTO
    ) -> ProductDTO: ...

    @abstractmethod
    async def admin_set_archived(
        self, admin_id: int, product_id: int, archived: bool
    ) -> ProductDTO: ...

    # Never lets stock go below zero.
    @abstractmethod
    async def admin_adjust_stock(
        self, admin_id: int, product_id: int, delta: int
    ) -> ProductDTO: ...
