from __future__ import annotations

import logging

from app.application.dtos.product_dto import (
    CategoryDTO,
    ProductCreateDTO,
    ProductDTO,
    ProductListDTO,
    ProductSearchParams,
    ProductUpdateDTO,
)
from app.application.iservices.iproduct_service import IProductService
from app.core.exceptions import ConflictError, NotFoundError
from app.infrastructure.irepositories.iaudit_log_repository import IAuditLogRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository

logger = logging.getLogger(__name__)


class ProductService(IProductService):
    def __init__(self, products: IProductRepository, audit: IAuditLogRepository) -> None:
        self._products = products
        self._audit = audit

    async def search(self, params: ProductSearchParams) -> ProductListDTO:
        return await self._products.search(params)

    async def get(self, product_id: int) -> ProductDTO:
        product = await self._products.get(product_id)
        if product is None or product.is_archived:
            raise NotFoundError("Product not found")
        return product

    async def admin_get(self, product_id: int) -> ProductDTO:
        product = await self._products.get(product_id)
        if product is None:
            raise NotFoundError("Product not found")
        return product

    async def list_categories(self) -> list[CategoryDTO]:
        return await self._products.list_categories()

    async def admin_create(self, admin_id: int, data: ProductCreateDTO) -> ProductDTO:
        if await self._products.get_category(data.category_id) is None:
            raise NotFoundError("Category not found")
        if await self._products.find_by_name(data.name) is not None:
            raise ConflictError("A product with this name already exists")
        product = await self._products.create(data)
        await self._audit.add(
            admin_id, "product_create", "product", product.id, {"name": product.name}
        )
        logger.info("admin_action=product_create admin_id=%s product_id=%s", admin_id, product.id)
        return product

    async def admin_update(
        self, admin_id: int, product_id: int, data: ProductUpdateDTO
    ) -> ProductDTO:
        if data.category_id is not None and (
            await self._products.get_category(data.category_id) is None
        ):
            raise NotFoundError("Category not found")
        product = await self._products.update(product_id, data)
        if product is None:
            raise NotFoundError("Product not found")
        changed = sorted(data.model_dump(exclude_none=True).keys())
        await self._audit.add(
            admin_id, "product_update", "product", product_id, {"fields": changed}
        )
        logger.info("admin_action=product_update admin_id=%s product_id=%s", admin_id, product_id)
        return product

    # Archiving hides the product from the catalog without deleting its order history.
    async def admin_set_archived(
        self, admin_id: int, product_id: int, archived: bool
    ) -> ProductDTO:
        product = await self._products.set_archived(product_id, archived)
        if product is None:
            raise NotFoundError("Product not found")
        await self._audit.add(
            admin_id,
            "product_archive" if archived else "product_unarchive",
            "product",
            product_id,
        )
        logger.info(
            "admin_action=product_%s admin_id=%s product_id=%s",
            "archive" if archived else "unarchive",
            admin_id,
            product_id,
        )
        return product

    async def admin_adjust_stock(self, admin_id: int, product_id: int, delta: int) -> ProductDTO:
        rows = await self._products.lock_products([product_id])
        if not rows:
            raise NotFoundError("Product not found")
        if rows[0].stock + delta < 0:
            raise ConflictError(f"Stock cannot go below zero (current stock: {rows[0].stock})")
        await self._products.apply_stock_delta(product_id, delta)
        await self._audit.add(
            admin_id,
            "stock_adjust",
            "product",
            product_id,
            {"delta": delta, "stock_after": rows[0].stock + delta},
        )
        logger.info(
            "admin_action=stock_adjust admin_id=%s product_id=%s delta=%s",
            admin_id,
            product_id,
            delta,
        )
        product = await self._products.get(product_id)
        assert product is not None
        return product
