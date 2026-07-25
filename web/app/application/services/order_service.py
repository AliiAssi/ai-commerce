from __future__ import annotations

import logging
from decimal import Decimal

from app.application.dtos.order_dto import OrderDTO, OrderItemCreateDTO, OrderStatus
from app.application.events.bus import EventBus
from app.application.events.definitions import OrderCancelled, OrderPlaced
from app.application.iservices.iorder_service import IOrderService
from app.core.exceptions import ConflictError, NotFoundError, OutOfStockError
from app.infrastructure.irepositories.iaudit_log_repository import IAuditLogRepository
from app.infrastructure.irepositories.icart_repository import ICartRepository
from app.infrastructure.irepositories.iorder_repository import IOrderRepository
from app.infrastructure.irepositories.iproduct_repository import IProductRepository

logger = logging.getLogger(__name__)

_NEXT_STATUS = {
    OrderStatus.PAID: OrderStatus.SHIPPED,
    OrderStatus.SHIPPED: OrderStatus.DELIVERED,
}


class OrderService(IOrderService):
    def __init__(
        self,
        orders: IOrderRepository,
        carts: ICartRepository,
        products: IProductRepository,
        events: EventBus,
        audit: IAuditLogRepository,
    ) -> None:
        self._orders = orders
        self._carts = carts
        self._products = products
        self._events = events
        self._audit = audit

    async def checkout(self, user_id: int) -> OrderDTO:
        cart = await self._carts.get_by_user(user_id)
        if cart is None or not cart.items:
            raise ConflictError("Cart is empty")

        wanted = {item.product_id: item.quantity for item in cart.items}
        locked = {row.id: row for row in await self._products.lock_products(sorted(wanted))}

        offenders = []
        for product_id, quantity in wanted.items():
            row = locked.get(product_id)
            if row is None or row.is_archived:
                offenders.append({"product_id": product_id, "reason": "unavailable"})
            elif row.stock < quantity:
                offenders.append(
                    {
                        "product_id": product_id,
                        "name": row.name,
                        "requested": quantity,
                        "available": row.stock,
                    }
                )
        if offenders:
            raise OutOfStockError(
                "Some items are not available in the requested quantity", details=offenders
            )

        items: list[OrderItemCreateDTO] = []
        total = Decimal("0.00")
        for product_id, quantity in wanted.items():
            row = locked[product_id]
            await self._products.apply_stock_delta(product_id, -quantity)
            items.append(
                OrderItemCreateDTO(
                    product_id=product_id,
                    product_name=row.name,
                    unit_price=row.price,
                    quantity=quantity,
                )
            )
            total += row.price * quantity

        order = await self._orders.create(user_id, items, total)
        await self._carts.clear(cart.id)
        self._events.publish(OrderPlaced(order_id=order.id, user_id=user_id, total=order.total))
        return order

    async def list_orders(self, user_id: int) -> list[OrderDTO]:
        return await self._orders.list_by_user(user_id)

    # Ownership check raises 404, not 403, so other users' order ids don't leak.
    async def get_order(self, user_id: int, order_id: int) -> OrderDTO:
        order = await self._orders.get(order_id)
        if order is None or order.user_id != user_id:
            raise NotFoundError("Order not found")
        return order

    async def cancel(self, user_id: int, order_id: int) -> OrderDTO:
        order = await self._orders.get_for_update(order_id)
        if order is None or order.user_id != user_id:
            raise NotFoundError("Order not found")
        if order.status != OrderStatus.PAID:
            raise ConflictError(f"Order can no longer be cancelled (status: {order.status})")

        await self._products.lock_products(sorted({item.product_id for item in order.items}))
        for item in order.items:
            await self._products.apply_stock_delta(item.product_id, item.quantity)
        await self._orders.set_status(order_id, OrderStatus.CANCELLED)
        self._events.publish(OrderCancelled(order_id=order_id, user_id=user_id))

        updated = await self._orders.get(order_id)
        assert updated is not None
        return updated

    async def admin_advance_status(self, admin_id: int, order_id: int) -> OrderDTO:
        order = await self._orders.get_for_update(order_id)
        if order is None:
            raise NotFoundError("Order not found")
        previous_status = order.status
        next_status = _NEXT_STATUS.get(previous_status)
        if next_status is None:
            raise ConflictError(f"Order in status '{previous_status}' cannot be advanced")
        await self._orders.set_status(order_id, next_status)
        await self._audit.add(
            admin_id,
            "order_status_advance",
            "order",
            order_id,
            {"from": previous_status, "to": next_status},
        )
        logger.info(
            "admin_action=order_status_advance admin_id=%s order_id=%s from=%s to=%s",
            admin_id,
            order_id,
            previous_status,
            next_status,
        )
        updated = await self._orders.get(order_id)
        assert updated is not None
        return updated
