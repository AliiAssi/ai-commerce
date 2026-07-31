from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.search_params import ProductSearchParams
from app.application.dtos.store_read_dto import (
    CategoryProductCountDTO,
    CategoryReadDTO,
    ProductPageDTO,
    ProductReadDTO,
    StoreStatsDTO,
)
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository

_SORTS = {
    "newest": (products.c.created_at.desc(), products.c.id.desc()),
    "price_asc": (products.c.price.asc(), products.c.id.asc()),
    "price_desc": (products.c.price.desc(), products.c.id.asc()),
    "rating": (products.c.rating_avg.desc(), products.c.review_count.desc(), products.c.id.asc()),
}


def _base_select() -> Select:
    return select(
        products.c.id,
        products.c.name,
        products.c.description,
        products.c.origin,
        products.c.price,
        products.c.stock,
        products.c.image_url,
        products.c.rating_avg,
        products.c.review_count,
        products.c.created_at,
        categories.c.name.label("category"),
        categories.c.slug.label("category_slug"),
    ).select_from(products.join(categories, products.c.category_id == categories.c.id))


def _product(row: Any) -> ProductReadDTO:
    return ProductReadDTO(**row)


class ProductReadRepository(IProductReadRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, params: ProductSearchParams) -> ProductPageDTO:
        stmt = _base_select().where(products.c.is_archived.is_(False))
        if params.query:
            tsquery = func.websearch_to_tsquery("english", params.query)
            stmt = stmt.where(products.c.search_vector.op("@@")(tsquery))
        if params.category_slug:
            stmt = stmt.where(categories.c.slug == params.category_slug)
        if params.min_price is not None:
            stmt = stmt.where(products.c.price >= params.min_price)
        if params.max_price is not None:
            stmt = stmt.where(products.c.price <= params.max_price)
        if params.in_stock_only:
            stmt = stmt.where(products.c.stock > 0)

        total = await self._session.scalar(
            stmt.with_only_columns(func.count(products.c.id), maintain_column_froms=True).order_by(
                None
            )
        )

        if params.sort == "relevance" and params.query:
            rank = func.ts_rank(
                products.c.search_vector, func.websearch_to_tsquery("english", params.query)
            )
            order = (rank.desc(), products.c.id.asc())
        else:
            order = _SORTS.get(params.sort, _SORTS["rating"])
        stmt = (
            stmt.order_by(*order)
            .limit(params.page_size)
            .offset((params.page - 1) * params.page_size)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return ProductPageDTO(
            items=[_product(row) for row in rows],
            total=total or 0,
            page=params.page,
            page_size=params.page_size,
        )

    async def by_ids(self, product_ids: Sequence[int]) -> list[ProductReadDTO]:
        if not product_ids:
            return []
        stmt = _base_select().where(
            products.c.id.in_(list(product_ids)), products.c.is_archived.is_(False)
        )
        rows = {row["id"]: row for row in (await self._session.execute(stmt)).mappings()}
        return [_product(rows[pid]) for pid in product_ids if pid in rows]

    async def get(self, product_id: int) -> ProductReadDTO | None:
        stmt = _base_select().where(products.c.id == product_id, products.c.is_archived.is_(False))
        row = (await self._session.execute(stmt)).mappings().first()
        return None if row is None else _product(row)

    async def list_categories(self) -> list[CategoryReadDTO]:
        live_products = func.count(products.c.id).filter(products.c.is_archived.is_(False))
        stmt = (
            select(
                categories.c.id,
                categories.c.name,
                categories.c.slug,
                live_products.label("product_count"),
            )
            .select_from(categories.outerjoin(products, products.c.category_id == categories.c.id))
            .group_by(categories.c.id, categories.c.name, categories.c.slug)
            .order_by(categories.c.name)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return [CategoryReadDTO(**row) for row in rows]

    async def top_rated(self, limit: int) -> list[ProductReadDTO]:
        stmt = (
            _base_select()
            .where(products.c.is_archived.is_(False), products.c.review_count > 0)
            .order_by(*_SORTS["rating"])
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return [_product(row) for row in rows]

    async def low_stock(self, limit: int) -> list[ProductReadDTO]:
        stmt = (
            _base_select()
            .where(products.c.is_archived.is_(False))
            .order_by(products.c.stock.asc(), products.c.id.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return [_product(row) for row in rows]

    async def stats(self) -> StoreStatsDTO:
        totals = (
            await self._session.execute(
                select(
                    func.count(products.c.id),
                    func.min(products.c.price),
                    func.max(products.c.price),
                    func.avg(products.c.price),
                ).where(products.c.is_archived.is_(False))
            )
        ).one()
        category_count = await self._session.scalar(select(func.count(categories.c.id)))
        top_stmt = (
            select(
                categories.c.name,
                categories.c.slug,
                func.count(products.c.id).label("product_count"),
            )
            .select_from(categories.join(products, products.c.category_id == categories.c.id))
            .where(products.c.is_archived.is_(False))
            .group_by(categories.c.name, categories.c.slug)
            .order_by(func.count(products.c.id).desc(), categories.c.name)
            .limit(5)
        )
        top_rows = (await self._session.execute(top_stmt)).mappings().all()

        price_avg = totals[3]
        return StoreStatsDTO(
            product_count=totals[0],
            category_count=category_count or 0,
            price_min=totals[1],
            price_max=totals[2],
            price_avg=None if price_avg is None else Decimal(price_avg).quantize(Decimal("0.01")),
            top_categories=[CategoryProductCountDTO(**row) for row in top_rows],
        )
