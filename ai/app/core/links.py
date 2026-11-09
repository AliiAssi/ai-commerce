from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlencode

Medium = Literal["chat", "mcp"]

_UTM_SOURCE = "assistant"

_REF = re.compile(
    r"(?P<kind>product|order):(?P<id>[1-9]\d{0,9})"
    r"|category:(?P<slug>[A-Za-z0-9][A-Za-z0-9_-]{0,99})"
    r"|search:(?P<query>[A-Za-z0-9%+=&._~-]*)"
)

_DEFAULT_SORT = {True: "relevance", False: "newest"}


def product_ref(product_id: int) -> str:
    return f"product:{product_id}"


def category_ref(slug: str) -> str:
    return f"category:{slug}"


def order_ref(order_id: int) -> str:
    return f"order:{order_id}"


def _price(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def search_ref(
    *,
    query: str | None,
    category_slug: str | None,
    min_price: float | None,
    max_price: float | None,
    in_stock_only: bool,
    sort: str,
) -> str:
    has_query = bool(query and query.strip())
    params = {
        "q": (query or "").strip(),
        "category": category_slug or "",
        "min_price": _price(min_price),
        "max_price": _price(max_price),
        "in_stock_only": "true" if in_stock_only else "",
        "sort": "" if sort == _DEFAULT_SORT[has_query] else sort,
    }
    return "search:" + urlencode({k: v for k, v in params.items() if v})


def ref_kind(ref: str) -> str | None:
    match = _REF.fullmatch(ref)
    return None if match is None else ref.partition(":")[0]


def ref_path(ref: str) -> str | None:
    match = _REF.fullmatch(ref)
    if match is None:
        return None
    if match["kind"] == "product":
        return f"/products/{match['id']}"
    if match["kind"] == "order":
        return f"/account/orders/{match['id']}"
    if match["slug"] is not None:
        return "/catalog?" + urlencode({"category": match["slug"]})
    query = match["query"]
    return f"/catalog?{query}" if query else "/catalog"


def tracked(path: str, medium: Medium) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urlencode({'utm_source': _UTM_SOURCE, 'utm_medium': medium})}"


def absolute(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path
