from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def test_list_pagination_envelope(client, catalog):
    response = await client.get("/api/v1/products")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["pages"] == 1
    assert len(body["items"]) == 3


async def test_full_text_search(client, catalog):
    response = await client.get("/api/v1/products", params={"q": "waterproof tent"})
    names = [p["name"] for p in response.json()["items"]]
    assert names == ["Alpha Tent"]


async def test_price_filter_and_sort(client, catalog):
    response = await client.get(
        "/api/v1/products", params={"min_price": 20, "max_price": 50, "sort": "price_asc"}
    )
    names = [p["name"] for p in response.json()["items"]]
    assert names == ["Beta Stove"]

    response = await client.get("/api/v1/products", params={"sort": "price_asc"})
    prices = [p["price"] for p in response.json()["items"]]
    assert prices == ["15.00", "25.50", "100.00"]


async def test_category_filter(client, catalog):
    response = await client.get("/api/v1/products", params={"category": "gear"})
    assert response.json()["total"] == 3
    response = await client.get("/api/v1/products", params={"category": "nope"})
    assert response.json()["total"] == 0


async def test_page_size_and_page(client, catalog):
    response = await client.get("/api/v1/products", params={"page_size": 2, "page": 2})
    body = response.json()
    assert body["pages"] == 2
    assert len(body["items"]) == 1


async def test_out_of_stock_still_visible(client, catalog):
    response = await client.get(f"/api/v1/products/{catalog['gamma'].id}")
    assert response.status_code == 200
    assert response.json()["stock"] == 0


async def test_product_404_shape(client, catalog):
    response = await client.get("/api/v1/products/99999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_categories_with_counts(client, catalog):
    response = await client.get("/api/v1/categories")
    assert response.status_code == 200
    (gear,) = response.json()
    assert gear["slug"] == "gear"
    assert gear["product_count"] == 3
