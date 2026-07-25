from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.product_dto import (
    CategoryDTO,
    ProductCreateDTO,
    ProductDTO,
    ProductListDTO,
    ProductSearchParams,
    ProductStockDTO,
    ProductUpdateDTO,
)
from app.infrastructure.irepositories.iproduct_repository import IProductRepository
from app.infrastructure.models.product import Category, Product

_SORTS = {
    "newest": lambda: (Product.created_at.desc(), Product.id.desc()),
    "price_asc": lambda: (Product.price.asc(), Product.id.asc()),
    "price_desc": lambda: (Product.price.desc(), Product.id.desc()),
    "rating": lambda: (Product.rating_avg.desc(), Product.review_count.desc(), Product.id.desc()),
}


class ProductRepository(IProductRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_dto(product: Product) -> ProductDTO:
        return ProductDTO(
            id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            stock=product.stock,
            origin=product.origin,
            image_url=product.image_url,
            rating_avg=product.rating_avg,
            review_count=product.review_count,
            is_archived=product.is_archived,
            category_id=product.category_id,
            category_name=product.category.name,
            category_slug=product.category.slug,
            created_at=product.created_at,
        )

    # The admin area filters by archived state and stock ceiling through these same params.
    async def search(self, params: ProductSearchParams) -> ProductListDTO:
        stmt = select(Product)
        if params.archived_only:
            stmt = stmt.where(Product.is_archived.is_(True))
        elif not params.include_archived:
            stmt = stmt.where(Product.is_archived.is_(False))
        if params.max_stock is not None:
            stmt = stmt.where(Product.stock <= params.max_stock)
        if params.q:
            stmt = stmt.where(
                Product.search_vector.op("@@")(func.websearch_to_tsquery("english", params.q))
            )
        if params.category_slug:
            stmt = stmt.join(Category, Product.category_id == Category.id).where(
                Category.slug == params.category_slug
            )
        if params.min_price is not None:
            stmt = stmt.where(Product.price >= params.min_price)
        if params.max_price is not None:
            stmt = stmt.where(Product.price <= params.max_price)

        count_stmt = stmt.with_only_columns(
            func.count(Product.id), maintain_column_froms=True
        ).order_by(None)
        total = await self._session.scalar(count_stmt) or 0

        stmt = (
            stmt.order_by(*_SORTS[params.sort]())
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
        products = (await self._session.scalars(stmt)).all()
        return ProductListDTO(
            items=[self._to_dto(p) for p in products],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get(self, product_id: int) -> ProductDTO | None:
        product = await self._session.scalar(
            select(Product)
            .where(Product.id == product_id)
            .execution_options(populate_existing=True)
        )
        return self._to_dto(product) if product else None

    async def find_by_name(self, name: str) -> ProductDTO | None:
        product = await self._session.scalar(
            select(Product)
            .where(func.lower(Product.name) == name.lower())
            .execution_options(populate_existing=True)
        )
        return self._to_dto(product) if product else None

    async def create(self, data: ProductCreateDTO) -> ProductDTO:
        product = Product(
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
            category_id=data.category_id,
            origin=data.origin,
            image_url=data.image_url,
        )
        self._session.add(product)
        await self._session.flush()
        created = await self.get(product.id)
        assert created is not None
        return created

    async def update(self, product_id: int, data: ProductUpdateDTO) -> ProductDTO | None:
        product = await self._session.get(Product, product_id)
        if product is None:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(product, field, value)
        await self._session.flush()
        return await self.get(product_id)

    async def set_archived(self, product_id: int, archived: bool) -> ProductDTO | None:
        product = await self._session.get(Product, product_id)
        if product is None:
            return None
        product.is_archived = archived
        await self._session.flush()
        return await self.get(product_id)

    # Ascending id order keeps lock acquisition order deterministic, avoiding deadlocks.
    async def lock_products(self, product_ids: list[int]) -> list[ProductStockDTO]:
        stmt = (
            select(Product.id, Product.name, Product.price, Product.stock, Product.is_archived)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            ProductStockDTO(
                id=row.id,
                name=row.name,
                price=row.price,
                stock=row.stock,
                is_archived=row.is_archived,
            )
            for row in rows
        ]

    # Caller must hold the row lock from lock_products first.
    async def apply_stock_delta(self, product_id: int, delta: int) -> None:
        await self._session.execute(
            update(Product).where(Product.id == product_id).values(stock=Product.stock + delta)
        )

    async def update_rating(self, product_id: int, rating_avg: Decimal, review_count: int) -> None:
        await self._session.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(rating_avg=rating_avg, review_count=review_count)
        )

    async def product_counts(self) -> tuple[int, int]:
        row = (
            await self._session.execute(
                select(
                    func.count(Product.id),
                    func.count(Product.id).filter(Product.is_archived.is_(False)),
                )
            )
        ).one()
        return row[0], row[1]

    async def low_stock(self, threshold: int, limit: int) -> list[ProductDTO]:
        products = (
            await self._session.scalars(
                select(Product)
                .where(Product.is_archived.is_(False), Product.stock <= threshold)
                .order_by(Product.stock.asc(), Product.id.asc())
                .limit(limit)
            )
        ).all()
        return [self._to_dto(p) for p in products]

    async def list_categories(self) -> list[CategoryDTO]:
        count = func.count(Product.id).filter(Product.is_archived.is_(False))
        stmt = (
            select(Category, count)
            .outerjoin(Product, Product.category_id == Category.id)
            .group_by(Category.id)
            .order_by(Category.name)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            CategoryDTO(id=cat.id, name=cat.name, slug=cat.slug, product_count=cnt)
            for cat, cnt in rows
        ]

    async def get_category(self, category_id: int) -> CategoryDTO | None:
        category = await self._session.get(Category, category_id)
        if category is None:
            return None
        return CategoryDTO(id=category.id, name=category.name, slug=category.slug)

    async def get_category_by_slug(self, slug: str) -> CategoryDTO | None:
        category = await self._session.scalar(select(Category).where(Category.slug == slug))
        if category is None:
            return None
        return CategoryDTO(id=category.id, name=category.name, slug=category.slug)

    async def create_category(self, name: str, slug: str) -> CategoryDTO:
        category = Category(name=name, slug=slug)
        self._session.add(category)
        await self._session.flush()
        return CategoryDTO(id=category.id, name=category.name, slug=category.slug)
