from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.product_dto import ProductListDTO, ProductSearchParams


class ICatalogSearchService(ABC):
    """Public catalog search: route to the AI service, or serve lexical.

    Separate from IProductService because it must not hold a database session — it calls
    another service mid-request. IProductService keeps the browse, detail, and admin paths,
    which are ordinary session-scoped work.
    """

    @abstractmethod
    async def search(self, params: ProductSearchParams) -> ProductListDTO: ...
