from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from app.application.dtos.product_dto import ProductSearchParams
from app.application.iservices.iproduct_service import IProductService
from app.core.auth import AuthenticatedUser, get_optional_user
from app.core.container import Injected
from app.presentation.templates import render

router = APIRouter()

_SORTS = {"newest", "price_asc", "price_desc", "rating"}
_PAGE_SIZE = 12


def _decimal_or_none(raw: str) -> Decimal | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


@router.get("/catalog")
async def catalog(
    request: Request,
    q: str = "",
    category: str = "",
    min_price: str = "",
    max_price: str = "",
    sort: str = "newest",
    page: int = 1,
    user: AuthenticatedUser | None = Depends(get_optional_user),
    products: IProductService = Injected(IProductService),
):
    params = ProductSearchParams(
        q=q.strip() or None,
        category_slug=category.strip() or None,
        min_price=_decimal_or_none(min_price),
        max_price=_decimal_or_none(max_price),
        sort=sort if sort in _SORTS else "newest",
        page=max(page, 1),
        page_size=_PAGE_SIZE,
    )
    result = await products.search(params)

    query = {
        "q": params.q or "",
        "category": params.category_slug or "",
        "min_price": min_price.strip(),
        "max_price": max_price.strip(),
        "sort": params.sort,
    }
    context = {
        "params": params,
        "products": result.items,
        "total": result.total,
        "page": result.page,
        "pages": (result.total + _PAGE_SIZE - 1) // _PAGE_SIZE,
        "qs": urlencode({k: v for k, v in query.items() if v}),
    }

    if request.headers.get("HX-Request") == "true":
        return render(request, "partials/product_grid.html", context, user=user)

    categories = await products.list_categories()
    context["category_options"] = [("", "All")] + [(c.slug, c.name) for c in categories]
    # Every category link keeps the other filters; re-selecting the active one clears it.
    context["category_links"] = [
        {
            "name": c.name,
            "count": c.product_count,
            "active": c.slug == params.category_slug,
            "href": _href(query, category="" if c.slug == params.category_slug else c.slug),
        }
        for c in categories
    ]
    context["clear_href"] = "/catalog"
    return render(request, "pages/catalog.html", context, user=user)


@router.get("/partials/shelves")
async def shelves(
    request: Request,
    products: IProductService = Injected(IProductService),
):
    categories = await products.list_categories()
    return render(request, "components/shelves.html", {"categories": categories})


def _href(query: dict[str, str], **overrides: str) -> str:
    merged = {**query, **overrides, "page": ""}
    encoded = urlencode({k: v for k, v in merged.items() if v})
    return f"/catalog?{encoded}" if encoded else "/catalog"
