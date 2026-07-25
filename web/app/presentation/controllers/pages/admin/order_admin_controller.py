from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from app.application.dtos.order_dto import OrderSearchParams, OrderStatus
from app.application.iservices.iadmin_service import IAdminService
from app.application.iservices.iorder_service import IOrderService
from app.core.auth import AuthenticatedUser
from app.core.authz import Permission
from app.core.container import Injected
from app.presentation.guards import require_permission
from app.presentation.templates import render, templates

router = APIRouter(prefix="/admin/orders")

_manage = require_permission(Permission.ORDERS_MANAGE)
_PAGE_SIZE = 15
_STATUS_VALUES = {s.value for s in OrderStatus}


@router.get("")
async def order_list(
    request: Request,
    status: str = "",
    page: int = 1,
    admin: AuthenticatedUser = Depends(_manage),
    admin_service: IAdminService = Injected(IAdminService),
):
    parsed = OrderStatus(status) if status in _STATUS_VALUES else None
    result = await admin_service.list_orders(
        OrderSearchParams(status=parsed, page=max(page, 1), page_size=_PAGE_SIZE)
    )
    counts = await admin_service.order_status_counts()
    return render(
        request,
        "admin/orders.html",
        {
            "orders": result.items,
            "page": result.page,
            "pages": (result.total + _PAGE_SIZE - 1) // _PAGE_SIZE,
            "qs": urlencode({"status": status}) if parsed else "",
            "status": status if parsed else "",
            "counts": counts,
            "total_all": sum(counts.values()),
            "active_nav": "orders",
        },
        user=admin,
    )


@router.post("/{order_id}/advance")
async def advance_order(
    request: Request,
    order_id: int,
    admin: AuthenticatedUser = Depends(_manage),
    orders: IOrderService = Injected(IOrderService),
):
    order = await orders.admin_advance_status(admin.id, order_id)
    return templates.TemplateResponse(
        request,
        "partials/admin/order_row.html",
        {"order": order, "toast_message": f"Order #{order.id} marked {order.status.value}"},
    )
