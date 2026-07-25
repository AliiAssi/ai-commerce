from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.dtos.product_dto import ProductCreateDTO, ProductUpdateDTO
from app.application.iservices.iorder_service import IOrderService
from app.application.iservices.iproduct_service import IProductService
from app.core.auth import AuthenticatedUser
from app.core.authz import Permission
from app.core.container import Injected
from app.presentation.guards import require_permission
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
