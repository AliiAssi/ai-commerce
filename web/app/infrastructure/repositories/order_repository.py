from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.order_dto import (
    AdminOrderPageDTO,
    OrderDTO,
    OrderItemCreateDTO,
    OrderItemDTO,
    OrderSearchParams,
    OrderStatus,
)
from app.infrastructure.irepositories.iorder_repository import IOrderRepository
from app.infrastructure.models.order import Order, OrderItem
from app.infrastructure.models.user import User


class OrderRepository(IOrderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_dto(order: Order) -> OrderDTO:
        items = [
            OrderItemDTO(
                product_id=item.product_id,
                product_name=item.product_name,
                unit_price=item.unit_price,
                quantity=item.quantity,
                line_total=item.unit_price * item.quantity,
            )
            for item in order.items
        ]
        return OrderDTO(
            id=order.id,
            user_id=order.user_id,
            status=order.status,
            total=order.total,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=items,
        )

    async def create(
        self,
        user_id: int,
        items: list[OrderItemCreateDTO],
        total: Decimal,
        status: OrderStatus = OrderStatus.PAID,
    ) -> OrderDTO:
        order = Order(
            user_id=user_id,
            status=status,
            total=total,
            items=[
                OrderItem(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                )
                for item in items
            ],
        )
        self._session.add(order)
        await self._session.flush()
        await self._session.refresh(order)
        return self._to_dto(order)

    # populate_existing picks up status changes written via core UPDATE earlier in this request.
    async def get(self, order_id: int) -> OrderDTO | None:
        order = await self._session.scalar(
            select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
        )
        return self._to_dto(order) if order else None

    async def get_for_update(self, order_id: int) -> OrderDTO | None:
        order = await self._session.scalar(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self._to_dto(order) if order else None

    async def list_by_user(self, user_id: int) -> list[OrderDTO]:
        orders = (
            await self._session.scalars(
                select(Order)
                .where(Order.user_id == user_id)
                .order_by(Order.created_at.desc(), Order.id.desc())
                .execution_options(populate_existing=True)
            )
        ).all()
        return [self._to_dto(order) for order in orders]

    async def search_all(self, params: OrderSearchParams) -> AdminOrderPageDTO:
        stmt = select(Order, User.email).join(User, Order.user_id == User.id)
        if params.status is not None:
            stmt = stmt.where(Order.status == params.status)

        count_stmt = stmt.with_only_columns(
            func.count(Order.id), maintain_column_froms=True
        ).order_by(None)
        total = await self._session.scalar(count_stmt) or 0

        rows = (
            await self._session.execute(
                stmt.order_by(Order.created_at.desc(), Order.id.desc())
                .offset((params.page - 1) * params.page_size)
                .limit(params.page_size)
                .execution_options(populate_existing=True)
            )
        ).all()
        items = []
        for order, email in rows:
            dto = self._to_dto(order)
            dto.user_email = email
            items.append(dto)
        return AdminOrderPageDTO(
            items=items, total=total, page=params.page, page_size=params.page_size
        )

    async def counts_by_status(self) -> dict[str, int]:
        rows = (
            await self._session.execute(
                select(Order.status, func.count(Order.id)).group_by(Order.status)
            )
        ).all()
        return {status.value: count for status, count in rows}

    async def revenue_total(self) -> Decimal:
        value = await self._session.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.status != OrderStatus.CANCELLED
            )
        )
        return Decimal(value)

    async def set_status(self, order_id: int, status: OrderStatus) -> None:
        await self._session.execute(
            update(Order).where(Order.id == order_id).values(status=status, updated_at=func.now())
        )

    async def user_purchased_product(self, user_id: int, product_id: int) -> bool:
        row = await self._session.scalar(
            select(OrderItem.id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                OrderItem.product_id == product_id,
                Order.status != OrderStatus.CANCELLED,
            )
            .limit(1)
        )
        return row is not None

    async def user_has_orders(self, user_id: int) -> bool:
        row = await self._session.scalar(select(Order.id).where(Order.user_id == user_id).limit(1))
        return row is not None
