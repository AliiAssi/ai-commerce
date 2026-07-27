from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.application.dtos.order_dto import OrderSearchParams, OrderStatus
from app.application.dtos.product_dto import (
    ProductCreateDTO,
    ProductSearchParams,
    ProductUpdateDTO,
    SortOption,
)
from app.application.iservices.iadmin_service import IAdminService
from app.application.iservices.iorder_service import IOrderService
from app.application.iservices.iproduct_service import IProductService
from app.core.auth import AuthenticatedUser
from app.core.authz import Permission
from app.core.config import get_settings
from app.core.container import Injected
from app.presentation.guards import require_permission
from app.presentation.schemas.admin_schemas import (
    AdminOrderResponse,
    AdminStatsResponse,
    AuditLogResponse,
    OrderStatusCountsResponse,
)
from app.presentation.schemas.common import Page
from app.presentation.schemas.order_schemas import OrderResponse
from app.presentation.schemas.product_schemas import (
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
    StockAdjustRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_products_manage = require_permission(Permission.PRODUCTS_MANAGE)
_orders_manage = require_permission(Permission.ORDERS_MANAGE)
_admin_access = require_permission(Permission.ADMIN_ACCESS)
_audit_view = require_permission(Permission.AUDIT_VIEW)

ProductStatusFilter = Literal["all", "active", "archived", "low"]


@router.get("/dashboard", response_model=AdminStatsResponse, dependencies=[Depends(_admin_access)])
async def dashboard(
    admin_service: IAdminService = Injected(IAdminService),
) -> AdminStatsResponse:
    return AdminStatsResponse.from_dto(await admin_service.dashboard())


# Declared before any /orders/{...} route so the literal segment always wins.
@router.get(
    "/orders/status-counts",
    response_model=OrderStatusCountsResponse,
    dependencies=[Depends(_orders_manage)],
)
async def order_status_counts(
    admin_service: IAdminService = Injected(IAdminService),
) -> OrderStatusCountsResponse:
    return OrderStatusCountsResponse.from_counts(await admin_service.order_status_counts())


# `status` is typed as the enum, so an unknown value is a 422. The admin page it replaces
# silently coerces junk to "no filter"; a typed client would rather hear about the typo.
@router.get(
    "/orders", response_model=Page[AdminOrderResponse], dependencies=[Depends(_orders_manage)]
)
async def list_orders(
    status: OrderStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=100),
    admin_service: IAdminService = Injected(IAdminService),
) -> Page[AdminOrderResponse]:
    result = await admin_service.list_orders(
        OrderSearchParams(status=status, page=page, page_size=page_size)
    )
    return Page[AdminOrderResponse].build(
        items=[AdminOrderResponse.from_dto(dto) for dto in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/audit", response_model=Page[AuditLogResponse], dependencies=[Depends(_audit_view)])
async def audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin_service: IAdminService = Injected(IAdminService),
) -> Page[AuditLogResponse]:
    result = await admin_service.audit_page(page, page_size)
    return Page[AuditLogResponse].build(
        items=[AuditLogResponse.from_dto(dto) for dto in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


# The public GET /products cannot reach archived or low-stock rows — it never declares those
# params, and FastAPI drops unknown query params silently. This is the admin-only way in.
@router.get(
    "/products", response_model=Page[ProductResponse], dependencies=[Depends(_products_manage)]
)
async def list_products(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    status: ProductStatusFilter = "all",
    sort: SortOption = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=100),
    products: IProductService = Injected(IProductService),
) -> Page[ProductResponse]:
    params = ProductSearchParams(
        q=q,
        category_slug=category,
        sort=sort,
        page=page,
        page_size=page_size,
        include_archived=status in ("all", "low"),
        archived_only=status == "archived",
        max_stock=get_settings().LOW_STOCK_THRESHOLD if status == "low" else None,
    )
    result = await products.search(params)
    return Page[ProductResponse].build(
        items=[ProductResponse.from_dto(dto) for dto in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


# Unlike the public GET /products/{id}, this resolves archived products so the edit form can
# load one.
@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(_products_manage)],
)
async def get_product(
    product_id: int,
    products: IProductService = Injected(IProductService),
) -> ProductResponse:
    return ProductResponse.from_dto(await products.admin_get(product_id))


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    body: ProductCreateRequest,
    admin: AuthenticatedUser = Depends(_products_manage),
    products: IProductService = Injected(IProductService),
) -> ProductResponse:
    data = ProductCreateDTO(**body.model_dump())
    return ProductResponse.from_dto(await products.admin_create(admin.id, data))


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    body: ProductUpdateRequest,
    admin: AuthenticatedUser = Depends(_products_manage),
    products: IProductService = Injected(IProductService),
) -> ProductResponse:
    data = ProductUpdateDTO(**body.model_dump())
    return ProductResponse.from_dto(await products.admin_update(admin.id, product_id, data))


@router.post("/products/{product_id}/archive", response_model=ProductResponse)
async def archive_product(
    product_id: int,
    admin: AuthenticatedUser = Depends(_products_manage),
    products: IProductService = Injected(IProductService),
) -> ProductResponse:
    return ProductResponse.from_dto(await products.admin_set_archived(admin.id, product_id, True))


@router.post("/products/{product_id}/unarchive", response_model=ProductResponse)
async def unarchive_product(
    product_id: int,
    admin: AuthenticatedUser = Depends(_products_manage),
    products: IProductService = Injected(IProductService),
) -> ProductResponse:
    return ProductResponse.from_dto(await products.admin_set_archived(admin.id, product_id, False))


@router.patch("/products/{product_id}/stock", response_model=ProductResponse)
async def adjust_stock(
    product_id: int,
    body: StockAdjustRequest,
    admin: AuthenticatedUser = Depends(_products_manage),
    products: IProductService = Injected(IProductService),
) -> ProductResponse:
    return ProductResponse.from_dto(
        await products.admin_adjust_stock(admin.id, product_id, body.delta)
    )


@router.post("/orders/{order_id}/advance-status", response_model=OrderResponse)
async def advance_order_status(
    order_id: int,
    admin: AuthenticatedUser = Depends(_orders_manage),
    orders: IOrderService = Injected(IOrderService),
) -> OrderResponse:
    return OrderResponse.from_dto(await orders.admin_advance_status(admin.id, order_id))
