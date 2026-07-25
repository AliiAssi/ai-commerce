from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.store_read_dto import OrderItemReadDTO, OrderReadDTO
from app.infrastructure.database.store_tables import order_items, orders, users
from app.infrastructure.irepositories.iorder_read_repository import IOrderReadRepository


def _base_select() -> Select:
    return select(
        orders.c.id,
        orders.c.status,
        orders.c.total,
        orders.c.created_at,
        orders.c.updated_at,
        users.c.email.label("user_email"),
    ).select_from(orders.join(users, orders.c.user_id == users.c.id))


def _order(row: Any, items: list[OrderItemReadDTO]) -> OrderReadDTO:
    return OrderReadDTO(**row, items=items)


class OrderReadRepository(IOrderReadRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, order_id: int, user_email: str | None = None) -> OrderReadDTO | None:
        stmt = _base_select().where(orders.c.id == order_id)
        if user_email is not None:
            stmt = stmt.where(func.lower(users.c.email) == user_email.strip().lower())
        row = (await self._session.execute(stmt)).mappings().first()
        if row is None:
            return None
        items = await self._items_for([row["id"]])
        return _order(row, items.get(row["id"], []))

    async def list_for_user(self, user_email: str, limit: int) -> list[OrderReadDTO]:
        stmt = (
            _base_select()
            .where(func.lower(users.c.email) == user_email.strip().lower())
            .order_by(orders.c.created_at.desc(), orders.c.id.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        items = await self._items_for([row["id"] for row in rows])
        return [_order(row, items.get(row["id"], [])) for row in rows]

    async def _items_for(self, order_ids: list[int]) -> dict[int, list[OrderItemReadDTO]]:
        if not order_ids:
            return {}
        stmt = (
            select(
                order_items.c.order_id,
                order_items.c.product_id,
                order_items.c.product_name,
                order_items.c.unit_price,
                order_items.c.quantity,
            )
            .where(order_items.c.order_id.in_(order_ids))
            .order_by(order_items.c.id)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        grouped: dict[int, list[OrderItemReadDTO]] = defaultdict(list)
        for row in rows:
            grouped[row["order_id"]].append(
                OrderItemReadDTO(
                    product_id=row["product_id"],
                    product_name=row["product_name"],
                    unit_price=row["unit_price"],
                    quantity=row["quantity"],
                )
            )
        return grouped
