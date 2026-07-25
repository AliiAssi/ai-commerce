from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.order_dto import OrderItemCreateDTO, OrderStatus
from app.application.dtos.product_dto import ProductCreateDTO, ProductDTO
from app.application.dtos.user_dto import UserDTO
from app.application.jobs import seed_data
from app.core.auth import ADMIN_ROLE, CUSTOMER_ROLE, hash_password
from app.core.config import Settings, load_settings_or_exit
from app.core.container import Scope, container
from app.core.logging import setup_logging
from app.core.registry import configure
from app.infrastructure.irepositories.iorder_repository import IOrderRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository
from app.infrastructure.irepositories.ireview_repository import IReviewRepository
from app.infrastructure.irepositories.iuser_repository import IUserRepository


async def _ensure_user(
    users: IUserRepository, email: str, password: str, role: str, settings: Settings
) -> tuple[UserDTO, bool]:
    existing = await users.get_by_email(email)
    if existing is not None:
        return existing, False
    created = await users.create(email, hash_password(password, settings.BCRYPT_ROUNDS), role)
    return created, True


async def _seed(scope: Scope, settings: Settings) -> None:
    users = scope.resolve(IUserRepository)
    products = scope.resolve(IProductRepository)
    orders = scope.resolve(IOrderRepository)
    reviews = scope.resolve(IReviewRepository)

    _admin, admin_created = await _ensure_user(
        users, settings.SEED_ADMIN_EMAIL, settings.SEED_ADMIN_PASSWORD, ADMIN_ROLE, settings
    )
    customers: dict[str, UserDTO] = {}
    customers_created = 0
    for email, password in seed_data.CUSTOMERS:
        user, created = await _ensure_user(users, email, password, CUSTOMER_ROLE, settings)
        customers[email] = user
        customers_created += created

    categories_created = 0
    category_ids: dict[str, int] = {}
    for name, slug in seed_data.CATEGORIES:
        category = await products.get_category_by_slug(slug)
        if category is None:
            category = await products.create_category(name, slug)
            categories_created += 1
        category_ids[slug] = category.id

    products_created = 0
    by_name: dict[str, ProductDTO] = {}
    for slug, name, origin, price, stock, description, image_url in seed_data.PRODUCTS:
        product = await products.find_by_name(name)
        if product is None:
            product = await products.create(
                ProductCreateDTO(
                    name=name,
                    description=description,
                    origin=origin,
                    price=Decimal(price),
                    stock=stock,
                    category_id=category_ids[slug],
                    image_url=image_url,
                )
            )
            products_created += 1
        by_name[name] = product

    orders_created = 0
    had_orders = {email: await orders.user_has_orders(user.id) for email, user in customers.items()}
    for email, status, lines in seed_data.ORDERS:
        user = customers[email]
        if had_orders[email]:
            continue
        items = [
            OrderItemCreateDTO(
                product_id=by_name[name].id,
                product_name=name,
                unit_price=by_name[name].price,
                quantity=quantity,
            )
            for name, quantity in lines
        ]
        total = sum((item.unit_price * item.quantity for item in items), Decimal("0.00"))
        await orders.create(user.id, items, total, OrderStatus(status))
        orders_created += 1

    reviews_created = 0
    reviewed_products: set[int] = set()
    for email, product_name, rating, body in seed_data.REVIEWS:
        user = customers[email]
        product = by_name[product_name]
        reviewed_products.add(product.id)
        if await reviews.exists(product.id, user.id):
            continue
        await reviews.create(product.id, user.id, rating, body)
        reviews_created += 1

    for product_id in reviewed_products:
        rating_avg, review_count = await reviews.rating_stats(product_id)
        await products.update_rating(product_id, rating_avg, review_count)

    print(f"admin:      {settings.SEED_ADMIN_EMAIL} ({'created' if admin_created else 'exists'})")
    print(
        f"customers:  {customers_created} created / {len(customers)} total (password: Demo#12345)"
    )
    print(f"categories: {categories_created} created / {len(category_ids)} total")
    print(f"products:   {products_created} created / {len(by_name)} total")
    print(f"orders:     {orders_created} created")
    print(f"reviews:    {reviews_created} created")


_STORE_TABLES = "reviews, order_items, orders, cart_items, carts, products, categories, users"


async def _empty_store(session: AsyncSession) -> None:
    await session.execute(text(f"TRUNCATE {_STORE_TABLES} RESTART IDENTITY CASCADE"))


# connect, run the seed in one transaction, dispose
async def run(fresh: bool = False) -> None:
    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)
    assert container.session_factory is not None and container.engine is not None
    async with container.session_factory() as session, session.begin():
        if fresh:
            print("--fresh: emptying the store before seeding")
            await _empty_store(session)
        await _seed(Scope(container, session), settings)
    await container.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(fresh="--fresh" in sys.argv))
