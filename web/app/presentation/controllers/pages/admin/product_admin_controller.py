from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request

from app.application.dtos.product_dto import (
    ProductCreateDTO,
    ProductDTO,
    ProductSearchParams,
    ProductUpdateDTO,
)
from app.application.iservices.iproduct_service import IProductService
from app.core.auth import AuthenticatedUser
from app.core.authz import Permission
from app.core.config import get_settings
from app.core.container import Injected
from app.presentation.flash import flash_redirect
from app.presentation.guards import require_permission
from app.presentation.templates import render, templates

router = APIRouter(prefix="/admin/products")

_manage = require_permission(Permission.PRODUCTS_MANAGE)
_PAGE_SIZE = 15


def _row(request: Request, product: ProductDTO, message: str):
    return templates.TemplateResponse(
        request,
        "partials/admin/product_row.html",
        {"product": product, "toast_message": message},
    )


async def _category_options(products: IProductService) -> list[tuple[int | str, str]]:
    return [(c.id, c.name) for c in await products.list_categories()]


@router.get("")
async def product_list(
    request: Request,
    q: str = "",
    category: str = "",
    status: str = "all",
    page: int = 1,
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    params = ProductSearchParams(
        q=q.strip() or None,
        category_slug=category.strip() or None,
        sort="newest",
        page=max(page, 1),
        page_size=_PAGE_SIZE,
        include_archived=status in ("all", "low"),
        archived_only=status == "archived",
        max_stock=get_settings().LOW_STOCK_THRESHOLD if status == "low" else None,
    )
    result = await products.search(params)
    categories = await products.list_categories()
    query = {"q": params.q or "", "category": category.strip(), "status": status}
    return render(
        request,
        "admin/products.html",
        {
            "products": result.items,
            "total": result.total,
            "page": result.page,
            "pages": (result.total + _PAGE_SIZE - 1) // _PAGE_SIZE,
            "qs": urlencode({k: v for k, v in query.items() if v}),
            "q": params.q or "",
            "category": category.strip(),
            "status": status,
            "category_options": [("", "All")] + [(c.slug, c.name) for c in categories],
            "active_nav": "products",
        },
        user=admin,
    )


@router.get("/new")
async def new_product_form(
    request: Request,
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    return render(
        request,
        "admin/product_form.html",
        {
            "product": None,
            "category_options": await _category_options(products),
            "active_nav": "products",
        },
        user=admin,
    )


@router.post("/new")
async def create_product(
    name: str = Form(min_length=1, max_length=200),
    category_id: int = Form(),
    price: Decimal = Form(gt=0),
    stock: int = Form(ge=0),
    description: str = Form(min_length=1),
    origin: str = Form(default="", max_length=80),
    image_url: str = Form(default="", max_length=500),
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    data = ProductCreateDTO(
        name=name.strip(),
        description=description.strip(),
        origin=origin.strip() or None,
        price=price,
        stock=stock,
        category_id=category_id,
        image_url=image_url.strip() or None,
    )
    product = await products.admin_create(admin.id, data)
    return flash_redirect("/admin/products", f"Product '{product.name}' created")


@router.get("/{product_id}/edit")
async def edit_product_form(
    request: Request,
    product_id: int,
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    product = await products.admin_get(product_id)
    return render(
        request,
        "admin/product_form.html",
        {
            "product": product,
            "category_options": await _category_options(products),
            "active_nav": "products",
        },
        user=admin,
    )


@router.post("/{product_id}/edit")
async def update_product(
    product_id: int,
    name: str = Form(min_length=1, max_length=200),
    category_id: int = Form(),
    price: Decimal = Form(gt=0),
    description: str = Form(min_length=1),
    origin: str = Form(default="", max_length=80),
    image_url: str = Form(default="", max_length=500),
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    data = ProductUpdateDTO(
        name=name.strip(),
        description=description.strip(),
        origin=origin.strip() or None,
        price=price,
        category_id=category_id,
        image_url=image_url.strip() or None,
    )
    product = await products.admin_update(admin.id, product_id, data)
    return flash_redirect("/admin/products", f"Product '{product.name}' updated")


@router.post("/{product_id}/stock")
async def adjust_stock(
    request: Request,
    product_id: int,
    delta: int = Form(),
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    product = await products.admin_adjust_stock(admin.id, product_id, delta)
    if request.headers.get("HX-Request") == "true":
        return _row(request, product, f"Stock set to {product.stock}")
    back = request.headers.get("referer") or "/admin/products"
    return flash_redirect(back, f"Stock of '{product.name}' set to {product.stock}")


@router.post("/{product_id}/archive")
async def archive_product(
    request: Request,
    product_id: int,
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    product = await products.admin_set_archived(admin.id, product_id, True)
    return _row(request, product, f"'{product.name}' archived")


@router.post("/{product_id}/unarchive")
async def unarchive_product(
    request: Request,
    product_id: int,
    admin: AuthenticatedUser = Depends(_manage),
    products: IProductService = Injected(IProductService),
):
    product = await products.admin_set_archived(admin.id, product_id, False)
    return _row(request, product, f"'{product.name}' is live again")
