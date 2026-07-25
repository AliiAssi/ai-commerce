from __future__ import annotations

import os

import pytest

from tests.integration.conftest import auth_headers, make_admin, register_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def test_full_checkout_flow(client, catalog):
    token = await register_user(client, "buyer@it.test")
    headers = auth_headers(token)
    alpha, beta = catalog["alpha"], catalog["beta"]

    response = await client.post(
        "/api/v1/cart/items", json={"product_id": alpha.id, "quantity": 2}, headers=headers
    )
    assert response.status_code == 201
    response = await client.post(
        "/api/v1/cart/items", json={"product_id": beta.id, "quantity": 1}, headers=headers
    )
    cart = response.json()
    assert cart["total_quantity"] == 3
    assert cart["grand_total"] == "225.50"

    response = await client.post("/api/v1/checkout", headers=headers)
    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "paid"
    assert order["total"] == "225.50"

    response = await client.get(f"/api/v1/products/{alpha.id}")
    assert response.json()["stock"] == 3

    response = await client.get("/api/v1/cart", headers=headers)
    assert response.json()["items"] == []

    response = await client.get("/api/v1/orders", headers=headers)
    assert len(response.json()) == 1
    response = await client.get(f"/api/v1/orders/{order['id']}", headers=headers)
    assert len(response.json()["items"]) == 2


async def test_stock_validation_on_add(client, catalog):
    token = await register_user(client, "buyer@it.test")
    headers = auth_headers(token)

    response = await client.post(
        "/api/v1/cart/items", json={"product_id": catalog["gamma"].id}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "out_of_stock"

    response = await client.post(
        "/api/v1/cart/items",
        json={"product_id": catalog["beta"].id, "quantity": 3},
        headers=headers,
    )
    assert response.status_code == 409


async def test_checkout_empty_cart_409(client, catalog):
    token = await register_user(client, "buyer@it.test")
    response = await client.post("/api/v1/checkout", headers=auth_headers(token))
    assert response.status_code == 409


async def test_checkout_fails_when_stock_drops(client, catalog):
    beta = catalog["beta"]
    first = auth_headers(await register_user(client, "first@it.test"))
    second = auth_headers(await register_user(client, "second@it.test"))

    for headers in (first, second):
        response = await client.post(
            "/api/v1/cart/items", json={"product_id": beta.id, "quantity": 2}, headers=headers
        )
        assert response.status_code == 201

    assert (await client.post("/api/v1/checkout", headers=first)).status_code == 201
    response = await client.post("/api/v1/checkout", headers=second)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "out_of_stock"

    response = await client.get(f"/api/v1/products/{beta.id}")
    assert response.json()["stock"] == 0


async def test_cancel_restores_stock(client, catalog):
    alpha = catalog["alpha"]
    headers = auth_headers(await register_user(client, "buyer@it.test"))

    await client.post(
        "/api/v1/cart/items", json={"product_id": alpha.id, "quantity": 2}, headers=headers
    )
    order = (await client.post("/api/v1/checkout", headers=headers)).json()
    assert (await client.get(f"/api/v1/products/{alpha.id}")).json()["stock"] == 3

    response = await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert (await client.get(f"/api/v1/products/{alpha.id}")).json()["stock"] == 5

    response = await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers)
    assert response.status_code == 409


async def test_order_ownership_hidden(client, catalog):
    buyer = auth_headers(await register_user(client, "buyer@it.test"))
    other = auth_headers(await register_user(client, "other@it.test"))

    await client.post("/api/v1/cart/items", json={"product_id": catalog["alpha"].id}, headers=buyer)
    order = (await client.post("/api/v1/checkout", headers=buyer)).json()

    response = await client.get(f"/api/v1/orders/{order['id']}", headers=other)
    assert response.status_code == 404


async def test_admin_403_for_customers(client, catalog):
    headers = auth_headers(await register_user(client, "buyer@it.test"))
    response = await client.post(
        "/api/v1/admin/products",
        json={
            "name": "X",
            "description": "Y",
            "price": "1.00",
            "stock": 1,
            "category_id": catalog["category"].id,
        },
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_lifecycle_and_cancel_after_ship(client, catalog):
    admin = auth_headers(await make_admin(client))
    buyer = auth_headers(await register_user(client, "buyer@it.test"))
    alpha = catalog["alpha"]

    await client.post("/api/v1/cart/items", json={"product_id": alpha.id}, headers=buyer)
    order = (await client.post("/api/v1/checkout", headers=buyer)).json()

    response = await client.post(
        f"/api/v1/admin/orders/{order['id']}/advance-status", headers=admin
    )
    assert response.json()["status"] == "shipped"

    response = await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=buyer)
    assert response.status_code == 409

    response = await client.post(
        f"/api/v1/admin/orders/{order['id']}/advance-status", headers=admin
    )
    assert response.json()["status"] == "delivered"

    response = await client.post(
        f"/api/v1/admin/orders/{order['id']}/advance-status", headers=admin
    )
    assert response.status_code == 409


async def test_admin_product_management(client, catalog):
    admin = auth_headers(await make_admin(client))
    category_id = catalog["category"].id

    response = await client.post(
        "/api/v1/admin/products",
        json={
            "name": "Delta Compass",
            "description": "A reliable baseplate compass for navigation",
            "price": "12.00",
            "stock": 7,
            "category_id": category_id,
        },
        headers=admin,
    )
    assert response.status_code == 201
    product = response.json()

    response = await client.patch(
        f"/api/v1/admin/products/{product['id']}", json={"price": "14.00"}, headers=admin
    )
    assert response.json()["price"] == "14.00"

    response = await client.patch(
        f"/api/v1/admin/products/{product['id']}/stock", json={"delta": -7}, headers=admin
    )
    assert response.json()["stock"] == 0
    response = await client.patch(
        f"/api/v1/admin/products/{product['id']}/stock", json={"delta": -1}, headers=admin
    )
    assert response.status_code == 409

    response = await client.post(f"/api/v1/admin/products/{product['id']}/archive", headers=admin)
    assert response.json()["is_archived"] is True
    assert (await client.get(f"/api/v1/products/{product['id']}")).status_code == 404

    await client.post(f"/api/v1/admin/products/{product['id']}/unarchive", headers=admin)
    assert (await client.get(f"/api/v1/products/{product['id']}")).status_code == 200
