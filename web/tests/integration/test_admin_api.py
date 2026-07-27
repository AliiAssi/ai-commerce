from __future__ import annotations

import os

import pytest

from tests.integration.conftest import auth_headers, make_admin, register_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

READ_ENDPOINTS = [
    "/api/v1/admin/dashboard",
    "/api/v1/admin/orders",
    "/api/v1/admin/orders/status-counts",
    "/api/v1/admin/audit",
    "/api/v1/admin/products",
    "/api/v1/admin/products/1",
]


async def _demote(email: str) -> None:
    from sqlalchemy import text

    from app.core.container import container

    async with container.session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE users SET role = 'customer' WHERE email = :email"), {"email": email}
        )


# register a buyer, put one product in their cart, check out, return the order payload
async def _place_order(client, product_id: int, email: str = "buyer@it.test") -> dict:
    buyer = await register_user(client, email)
    await client.post(
        "/api/v1/cart/items", json={"product_id": product_id}, headers=auth_headers(buyer)
    )
    response = await client.post("/api/v1/checkout", headers=auth_headers(buyer))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("path", READ_ENDPOINTS)
async def test_read_endpoints_reject_anonymous(client, catalog, path):
    assert (await client.get(path)).status_code == 401


@pytest.mark.parametrize("path", READ_ENDPOINTS)
async def test_read_endpoints_reject_customer(client, catalog, path):
    token = await register_user(client, "plain@it.test")
    assert (await client.get(path, headers=auth_headers(token))).status_code == 403


async def test_demotion_takes_effect_immediately(client, catalog):
    token = await make_admin(client, "fired@it.test")
    headers = auth_headers(token)
    assert (await client.get("/api/v1/admin/dashboard", headers=headers)).status_code == 200

    await _demote("fired@it.test")

    assert (await client.get("/api/v1/admin/dashboard", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/admin/products", headers=headers)).status_code == 403


async def test_dashboard_reports_stats_and_low_stock(client, catalog):
    order = await _place_order(client, catalog["alpha"].id)
    token = await make_admin(client)
    headers = auth_headers(token)

    # every fixture product starts at or below LOW_STOCK_THRESHOLD (5), so restock one
    # well past it to prove the dashboard actually filters rather than listing everything
    restocked = await client.patch(
        f"/api/v1/admin/products/{catalog['alpha'].id}/stock", json={"delta": 46}, headers=headers
    )
    assert restocked.status_code == 200, restocked.text
    assert restocked.json()["stock"] == 50  # 5 - 1 sold + 46

    response = await client.get("/api/v1/admin/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["revenue"] == str(order["total"])
    assert body["orders_total"] == 1
    assert body["orders_by_status"]["paid"] == 1
    assert body["product_count"] == 3
    assert body["active_product_count"] == 3
    assert body["customer_count"] == 1  # the buyer; the admin is not a customer

    low_stock = {item["name"] for item in body["low_stock"]}
    assert low_stock == {"Beta Stove", "Gamma Lantern"}

    # the field OrderResponse cannot carry, which is why AdminOrderResponse exists
    assert body["recent_orders"][0]["user_email"] == "buyer@it.test"
    assert body["recent_activity"][0]["action"] == "stock_adjust"


async def test_order_list_carries_buyer_and_filters_by_status(client, catalog):
    order = await _place_order(client, catalog["alpha"].id)
    token = await make_admin(client)
    headers = auth_headers(token)

    response = await client.get("/api/v1/admin/orders", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [body["total"], body["page"], body["page_size"], body["pages"]] == [1, 1, 15, 1]

    row = body["items"][0]
    assert row["id"] == order["id"]
    assert row["user_email"] == "buyer@it.test"
    assert row["user_id"] > 0
    assert row["status"] == "paid"

    paid = await client.get("/api/v1/admin/orders", params={"status": "paid"}, headers=headers)
    assert paid.json()["total"] == 1

    cancelled = await client.get(
        "/api/v1/admin/orders", params={"status": "cancelled"}, headers=headers
    )
    assert cancelled.json()["total"] == 0


# the admin page silently ignores an unknown status; the API is typed, so it says so
async def test_order_list_rejects_unknown_status(client, catalog):
    token = await make_admin(client)
    response = await client.get(
        "/api/v1/admin/orders", params={"status": "bogus"}, headers=auth_headers(token)
    )
    assert response.status_code == 422


# the repository groups by status, so a status with no orders is a missing key there
async def test_status_counts_include_every_status(client, catalog):
    await _place_order(client, catalog["alpha"].id)
    token = await make_admin(client)

    response = await client.get("/api/v1/admin/orders/status-counts", headers=auth_headers(token))
    assert response.status_code == 200
    body = response.json()

    assert body["counts"] == {"paid": 1, "shipped": 0, "delivered": 0, "cancelled": 0}
    assert body["total"] == sum(body["counts"].values()) == 1


async def test_audit_page_records_admin_actions(client, catalog):
    token = await make_admin(client)
    headers = auth_headers(token)
    created = await client.post(
        "/api/v1/admin/products",
        json={
            "name": "Audited Kettle",
            "description": "A kettle created through the admin API",
            "price": "42.00",
            "stock": 4,
            "category_id": catalog["category"].id,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    response = await client.get("/api/v1/admin/audit", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [body["page"], body["page_size"]] == [1, 20]
    assert body["total"] >= 1

    entry = body["items"][0]
    assert entry["action"] == "product_create"
    assert entry["admin_email"] == "admin@it.test"
    assert entry["entity_id"] == created.json()["id"]


async def test_product_list_status_tabs(client, catalog):
    token = await make_admin(client)
    headers = auth_headers(token)
    archived_id = catalog["gamma"].id
    assert (
        await client.post(f"/api/v1/admin/products/{archived_id}/archive", headers=headers)
    ).status_code == 200

    async def names(**params) -> set[str]:
        response = await client.get("/api/v1/admin/products", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return {item["name"] for item in response.json()["items"]}

    assert await names() == {"Alpha Tent", "Beta Stove", "Gamma Lantern"}
    assert await names(status="active") == {"Alpha Tent", "Beta Stove"}
    assert await names(status="archived") == {"Gamma Lantern"}
    # LOW_STOCK_THRESHOLD is 5: Alpha has exactly 5, Beta 2, Gamma 0
    assert await names(status="low") == {"Alpha Tent", "Beta Stove", "Gamma Lantern"}

    assert await names(q="stove") == {"Beta Stove"}
    assert await names(category="gear") == {"Alpha Tent", "Beta Stove", "Gamma Lantern"}
    assert await names(category="nope") == set()


# the whole point of G6: the edit form has to be able to load an archived product
async def test_admin_get_resolves_archived_product(client, catalog):
    token = await make_admin(client)
    headers = auth_headers(token)
    product_id = catalog["gamma"].id
    await client.post(f"/api/v1/admin/products/{product_id}/archive", headers=headers)

    admin_view = await client.get(f"/api/v1/admin/products/{product_id}", headers=headers)
    assert admin_view.status_code == 200
    assert admin_view.json()["is_archived"] is True

    assert (await client.get(f"/api/v1/products/{product_id}")).status_code == 404


async def test_admin_get_missing_product_is_404(client, catalog):
    token = await make_admin(client)
    response = await client.get("/api/v1/admin/products/9999", headers=auth_headers(token))
    assert response.status_code == 404


# The public endpoint never declares these params, so FastAPI drops them rather than
# rejecting them. Pin that they stay unreachable instead of quietly becoming a leak.
async def test_public_product_search_ignores_admin_only_params(client, catalog):
    token = await make_admin(client)
    await client.post(
        f"/api/v1/admin/products/{catalog['gamma'].id}/archive", headers=auth_headers(token)
    )

    response = await client.get(
        "/api/v1/products", params={"include_archived": "true", "archived_only": "true"}
    )
    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Alpha Tent", "Beta Stove"}
