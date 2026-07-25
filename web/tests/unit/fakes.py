from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.application.dtos.audit_dto import AuditLogDTO, AuditPageDTO
from app.application.dtos.cart_dto import CartDTO, CartItemDTO
from app.application.dtos.order_dto import (
    AdminOrderPageDTO,
    OrderDTO,
    OrderItemCreateDTO,
    OrderItemDTO,
    OrderSearchParams,
    OrderStatus,
)
from app.application.dtos.product_dto import (
    CategoryDTO,
    ProductCreateDTO,
    ProductDTO,
    ProductListDTO,
    ProductSearchParams,
    ProductStockDTO,
    ProductUpdateDTO,
)
from app.application.dtos.review_dto import ReviewDTO
from app.application.dtos.user_dto import UserCredentialsDTO, UserDTO
from app.infrastructure.irepositories.iaudit_log_repository import IAuditLogRepository
from app.infrastructure.irepositories.icart_repository import ICartRepository
from app.infrastructure.irepositories.iorder_repository import IOrderRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository
from app.infrastructure.irepositories.ireview_repository import IReviewRepository
from app.infrastructure.irepositories.iuser_repository import IUserRepository


def _now() -> datetime:
    return datetime.now(UTC)


class FakeProductRepository(IProductRepository):
    def __init__(self) -> None:
        self._products: dict[int, ProductDTO] = {}
        self._categories: dict[int, CategoryDTO] = {}
        self._next_product = 1
        self._next_category = 1

    # test helper: preload a product, creating a default category on demand
    def seed(
        self,
        name: str,
        price: str = "10.00",
        stock: int = 10,
        archived: bool = False,
    ) -> ProductDTO:
        if not self._categories:
            self._categories[1] = CategoryDTO(id=1, name="General", slug="general")
            self._next_category = 2
        category = next(iter(self._categories.values()))
        product = ProductDTO(
            id=self._next_product,
            name=name,
            description=f"{name} description",
            origin=None,
            price=Decimal(price),
            stock=stock,
            image_url=None,
            rating_avg=Decimal("0.00"),
            review_count=0,
            is_archived=archived,
            category_id=category.id,
            category_name=category.name,
            category_slug=category.slug,
            created_at=_now(),
        )
        self._products[product.id] = product
        self._next_product += 1
        return product

    async def search(self, params: ProductSearchParams) -> ProductListDTO:
        items = list(self._products.values())
        if params.archived_only:
            items = [p for p in items if p.is_archived]
        elif not params.include_archived:
            items = [p for p in items if not p.is_archived]
        if params.max_stock is not None:
            items = [p for p in items if p.stock <= params.max_stock]
        return ProductListDTO(
            items=items, total=len(items), page=params.page, page_size=params.page_size
        )

    async def product_counts(self) -> tuple[int, int]:
        total = len(self._products)
        active = sum(1 for p in self._products.values() if not p.is_archived)
        return total, active

    async def low_stock(self, threshold: int, limit: int) -> list[ProductDTO]:
        matching = [
            p for p in self._products.values() if not p.is_archived and p.stock <= threshold
        ]
        return sorted(matching, key=lambda p: (p.stock, p.id))[:limit]

    async def get(self, product_id: int) -> ProductDTO | None:
        return self._products.get(product_id)

    async def find_by_name(self, name: str) -> ProductDTO | None:
        return next((p for p in self._products.values() if p.name.lower() == name.lower()), None)

    async def create(self, data: ProductCreateDTO) -> ProductDTO:
        category = self._categories[data.category_id]
        product = ProductDTO(
            id=self._next_product,
            name=data.name,
            description=data.description,
            origin=data.origin,
            price=data.price,
            stock=data.stock,
            image_url=data.image_url,
            rating_avg=Decimal("0.00"),
            review_count=0,
            is_archived=False,
            category_id=category.id,
            category_name=category.name,
            category_slug=category.slug,
            created_at=_now(),
        )
        self._products[product.id] = product
        self._next_product += 1
        return product

    async def update(self, product_id: int, data: ProductUpdateDTO) -> ProductDTO | None:
        product = self._products.get(product_id)
        if product is None:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(product, field, value)
        return product

    async def set_archived(self, product_id: int, archived: bool) -> ProductDTO | None:
        product = self._products.get(product_id)
        if product is None:
            return None
        product.is_archived = archived
        return product

    async def lock_products(self, product_ids: list[int]) -> list[ProductStockDTO]:
        return [
            ProductStockDTO(
                id=p.id, name=p.name, price=p.price, stock=p.stock, is_archived=p.is_archived
            )
            for pid in sorted(set(product_ids))
            if (p := self._products.get(pid)) is not None
        ]

    async def apply_stock_delta(self, product_id: int, delta: int) -> None:
        self._products[product_id].stock += delta

    async def update_rating(self, product_id: int, rating_avg: Decimal, review_count: int) -> None:
        product = self._products[product_id]
        product.rating_avg = rating_avg
        product.review_count = review_count

    async def list_categories(self) -> list[CategoryDTO]:
        return list(self._categories.values())

    async def get_category(self, category_id: int) -> CategoryDTO | None:
        return self._categories.get(category_id)

    async def get_category_by_slug(self, slug: str) -> CategoryDTO | None:
        return next((c for c in self._categories.values() if c.slug == slug), None)

    async def create_category(self, name: str, slug: str) -> CategoryDTO:
        category = CategoryDTO(id=self._next_category, name=name, slug=slug)
        self._categories[category.id] = category
        self._next_category += 1
        return category


class FakeCartRepository(ICartRepository):
    def __init__(self, products: FakeProductRepository) -> None:
        self._products = products
        self._carts: dict[int, dict[int, int]] = {}
        self._cart_ids: dict[int, int] = {}
        self._next_cart = 1

    # build the dto from live product data, like the real repository does
    async def _to_dto(self, user_id: int) -> CartDTO:
        lines = self._carts[user_id]
        items = []
        for product_id, quantity in lines.items():
            product = await self._products.get(product_id)
            assert product is not None
            items.append(
                CartItemDTO(
                    product_id=product_id,
                    product_name=product.name,
                    unit_price=product.price,
                    quantity=quantity,
                    line_total=product.price * quantity,
                    available_stock=product.stock,
                    is_archived=product.is_archived,
                    image_url=product.image_url,
                )
            )
        return CartDTO(
            id=self._cart_ids[user_id],
            user_id=user_id,
            items=items,
            total_quantity=sum(i.quantity for i in items),
            grand_total=sum((i.line_total for i in items), Decimal("0.00")),
        )

    async def get_by_user(self, user_id: int) -> CartDTO | None:
        if user_id not in self._carts:
            return None
        return await self._to_dto(user_id)

    async def get_or_create(self, user_id: int) -> CartDTO:
        if user_id not in self._carts:
            self._carts[user_id] = {}
            self._cart_ids[user_id] = self._next_cart
            self._next_cart += 1
        return await self._to_dto(user_id)

    async def upsert_item(self, cart_id: int, product_id: int, quantity: int) -> None:
        user_id = next(u for u, c in self._cart_ids.items() if c == cart_id)
        self._carts[user_id][product_id] = quantity

    async def remove_item(self, cart_id: int, product_id: int) -> bool:
        user_id = next(u for u, c in self._cart_ids.items() if c == cart_id)
        return self._carts[user_id].pop(product_id, None) is not None

    async def clear(self, cart_id: int) -> None:
        user_id = next(u for u, c in self._cart_ids.items() if c == cart_id)
        self._carts[user_id] = {}


class FakeOrderRepository(IOrderRepository):
    def __init__(self) -> None:
        self._orders: dict[int, OrderDTO] = {}
        self._next = 1

    async def create(
        self,
        user_id: int,
        items: list[OrderItemCreateDTO],
        total: Decimal,
        status: OrderStatus = OrderStatus.PAID,
    ) -> OrderDTO:
        order = OrderDTO(
            id=self._next,
            user_id=user_id,
            status=status,
            total=total,
            created_at=_now(),
            updated_at=_now(),
            items=[
                OrderItemDTO(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    line_total=item.unit_price * item.quantity,
                )
                for item in items
            ],
        )
        self._orders[order.id] = order
        self._next += 1
        return order

    async def get(self, order_id: int) -> OrderDTO | None:
        return self._orders.get(order_id)

    async def get_for_update(self, order_id: int) -> OrderDTO | None:
        return self._orders.get(order_id)

    async def list_by_user(self, user_id: int) -> list[OrderDTO]:
        return sorted(
            (o for o in self._orders.values() if o.user_id == user_id),
            key=lambda o: o.id,
            reverse=True,
        )

    async def set_status(self, order_id: int, status: OrderStatus) -> None:
        self._orders[order_id].status = status
        self._orders[order_id].updated_at = _now()

    async def search_all(self, params: OrderSearchParams) -> AdminOrderPageDTO:
        orders = sorted(self._orders.values(), key=lambda o: o.id, reverse=True)
        if params.status is not None:
            orders = [o for o in orders if o.status == params.status]
        start = (params.page - 1) * params.page_size
        return AdminOrderPageDTO(
            items=orders[start : start + params.page_size],
            total=len(orders),
            page=params.page,
            page_size=params.page_size,
        )

    async def counts_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for order in self._orders.values():
            counts[order.status.value] = counts.get(order.status.value, 0) + 1
        return counts

    async def revenue_total(self) -> Decimal:
        return sum(
            (o.total for o in self._orders.values() if o.status != OrderStatus.CANCELLED),
            Decimal("0.00"),
        )

    async def user_purchased_product(self, user_id: int, product_id: int) -> bool:
        return any(
            order.user_id == user_id
            and order.status != OrderStatus.CANCELLED
            and any(item.product_id == product_id for item in order.items)
            for order in self._orders.values()
        )

    async def user_has_orders(self, user_id: int) -> bool:
        return any(order.user_id == user_id for order in self._orders.values())


class FakeUserRepository(IUserRepository):
    def __init__(self) -> None:
        self._users: dict[int, UserCredentialsDTO] = {}
        self._next = 1

    async def get(self, user_id: int) -> UserDTO | None:
        creds = self._users.get(user_id)
        if creds is None:
            return None
        return UserDTO(id=creds.id, email=creds.email, role=creds.role, created_at=creds.created_at)

    async def get_by_email(self, email: str) -> UserDTO | None:
        creds = await self.get_credentials(email)
        if creds is None:
            return None
        return UserDTO(id=creds.id, email=creds.email, role=creds.role, created_at=creds.created_at)

    async def get_credentials(self, email: str) -> UserCredentialsDTO | None:
        return next((u for u in self._users.values() if u.email == email), None)

    async def create(self, email: str, password_hash: str, role: str) -> UserDTO:
        creds = UserCredentialsDTO(
            id=self._next, email=email, role=role, password_hash=password_hash, created_at=_now()
        )
        self._users[creds.id] = creds
        self._next += 1
        return UserDTO(id=creds.id, email=creds.email, role=creds.role, created_at=creds.created_at)

    async def customer_count(self) -> int:
        return sum(1 for u in self._users.values() if u.role == "customer")


class FakeAuditLogRepository(IAuditLogRepository):
    def __init__(self) -> None:
        self.entries: list[AuditLogDTO] = []
        self._next = 1

    async def add(self, admin_id, action, entity_type, entity_id=None, detail=None) -> None:
        self.entries.append(
            AuditLogDTO(
                id=self._next,
                admin_id=admin_id,
                admin_email=f"admin{admin_id}@x.test",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                detail=detail,
                created_at=_now(),
            )
        )
        self._next += 1

    async def list(self, page: int, page_size: int) -> AuditPageDTO:
        newest = list(reversed(self.entries))
        start = (page - 1) * page_size
        return AuditPageDTO(
            items=newest[start : start + page_size],
            total=len(newest),
            page=page,
            page_size=page_size,
        )

    async def recent(self, limit: int) -> list[AuditLogDTO]:
        return list(reversed(self.entries))[:limit]


class FakeReviewRepository(IReviewRepository):
    def __init__(self, users: FakeUserRepository) -> None:
        self._users = users
        self._reviews: dict[int, ReviewDTO] = {}
        self._next = 1

    async def create(self, product_id: int, user_id: int, rating: int, text: str) -> ReviewDTO:
        user = await self._users.get(user_id)
        review = ReviewDTO(
            id=self._next,
            product_id=product_id,
            user_id=user_id,
            user_email=user.email if user else "",
            rating=rating,
            text=text,
            created_at=_now(),
        )
        self._reviews[review.id] = review
        self._next += 1
        return review

    async def list_by_product(self, product_id: int) -> list[ReviewDTO]:
        return sorted(
            (r for r in self._reviews.values() if r.product_id == product_id),
            key=lambda r: r.id,
            reverse=True,
        )

    async def exists(self, product_id: int, user_id: int) -> bool:
        return any(
            r.product_id == product_id and r.user_id == user_id for r in self._reviews.values()
        )

    async def rating_stats(self, product_id: int) -> tuple[Decimal, int]:
        ratings = [r.rating for r in self._reviews.values() if r.product_id == product_id]
        if not ratings:
            return Decimal("0.00"), 0
        average = (Decimal(sum(ratings)) / len(ratings)).quantize(Decimal("0.01"))
        return average, len(ratings)
