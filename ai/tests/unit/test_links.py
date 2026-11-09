from __future__ import annotations

import pytest

from app.core.links import absolute, ref_kind, ref_path, search_ref, tracked


@pytest.mark.parametrize(
    ("ref", "path"),
    [
        ("product:12", "/products/12"),
        ("order:7", "/account/orders/7"),
        ("category:olive-oil", "/catalog?category=olive-oil"),
        ("search:q=olive+oil&sort=rating", "/catalog?q=olive+oil&sort=rating"),
        ("search:", "/catalog"),
    ],
)
def test_known_refs_map_to_storefront_paths(ref: str, path: str) -> None:
    assert ref_path(ref) == path


@pytest.mark.parametrize(
    "ref",
    [
        "product:0",
        "product:abc",
        "product:12/../../admin",
        "order:-1",
        "category:",
        "category:a b",
        "search:q=<script>",
        "https://evil.example",
        "javascript:alert(1)",
        "/products/12",
    ],
)
def test_anything_else_is_not_a_ref(ref: str) -> None:
    assert ref_path(ref) is None
    assert ref_kind(ref) is None


def test_search_ref_mirrors_the_catalog_url_and_drops_default_sorts() -> None:
    with_query = search_ref(
        query=" olive oil ",
        category_slug="pantry",
        min_price=None,
        max_price=20.0,
        in_stock_only=True,
        sort="relevance",
    )
    browse = search_ref(
        query=None,
        category_slug=None,
        min_price=5.5,
        max_price=None,
        in_stock_only=False,
        sort="rating",
    )

    assert with_query == "search:q=olive+oil&category=pantry&max_price=20&in_stock_only=true"
    assert browse == "search:min_price=5.5&sort=rating"
    assert (
        ref_path(with_query)
        == "/catalog?q=olive+oil&category=pantry&max_price=20&in_stock_only=true"
    )


def test_tracking_and_absolute_urls() -> None:
    assert tracked("/products/1", "chat") == "/products/1?utm_source=assistant&utm_medium=chat"
    assert tracked("/catalog?q=x", "mcp") == "/catalog?q=x&utm_source=assistant&utm_medium=mcp"
    assert absolute("https://shop.example/", "/products/1") == "https://shop.example/products/1"
