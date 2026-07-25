from __future__ import annotations

import os

import pytest

from tests.integration.conftest import auth_headers, make_admin, register_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


# page auth uses cookies; helper turns a token payload into a cookie dict
def cookies(token_payload: dict) -> dict[str, str]:
    return {"access_token": token_payload["access_token"]}


async def _demote(email: str) -> None:
    from sqlalchemy import text

    from app.core.container import container

    async with container.session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE users SET role = 'customer' WHERE email = :email"), {"email": email}
        )


async def test_guest_is_redirected_to_login(client):
    response = await client.get("/admin")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


async def test_customer_gets_403_page(client, catalog):
    token = await register_user(client, "plain@it.test")
    response = await client.get("/admin", cookies=cookies(token))
    assert response.status_code == 403
    assert "restricted" in response.text


async def test_admin_sees_dashboard(client, catalog):
    token = await make_admin(client)
    response = await client.get("/admin", cookies=cookies(token))
    assert response.status_code == 200
    assert "Revenue" in response.text
    assert "Low stock" in response.text


async def test_demotion_takes_effect_immediately(client, catalog):
    token = await make_admin(client, "fired@it.test")
    assert (await client.get("/admin", cookies=cookies(token))).status_code == 200

    await _demote("fired@it.test")

    assert (await client.get("/admin", cookies=cookies(token))).status_code == 403
    api = await client.post("/api/v1/admin/orders/1/advance-status", headers=auth_headers(token))
    assert api.status_code == 403


async def test_product_create_edit_and_audit(client, catalog):
    token = await make_admin(client)
    jar = cookies(token)
    category_id = catalog["category"].id

    response = await client.post(
        "/admin/products/new",
        data={
            "name": "Admin Made Kettle",
            "category_id": category_id,
            "price": "42.00",
            "stock": "4",
            "description": "A kettle created through the admin UI",
        },
        cookies=jar,
    )
    assert response.status_code == 303

    listing = await client.get("/admin/products", cookies=jar)
    assert "Admin Made Kettle" in listing.text

    row = await client.post(
        "/admin/products/1/stock",
        data={"delta": "3"},
        cookies=jar,
        headers={"HX-Request": "true"},
    )
    assert row.status_code == 200
    assert 'id="prow-1"' in row.text

    audit = await client.get("/admin/audit", cookies=jar)
    assert "product_create" in audit.text
    assert "stock_adjust" in audit.text


async def test_low_stock_filter(client, catalog):
    token = await make_admin(client)
    jar = cookies(token)
    await client.post(
        f"/admin/products/{catalog['alpha'].id}/stock",
        data={"delta": "45"},
        cookies=jar,
        headers={"HX-Request": "true"},
    )
    response = await client.get("/admin/products", params={"status": "low"}, cookies=jar)
    assert "Beta Stove" in response.text
    assert "Alpha Tent" not in response.text


async def test_order_advance_from_admin_ui(client, catalog):
    buyer = await register_user(client, "buyer@it.test")
    await client.post(
        "/api/v1/cart/items",
        json={"product_id": catalog["alpha"].id},
        headers=auth_headers(buyer),
    )
    order = (await client.post("/api/v1/checkout", headers=auth_headers(buyer))).json()

    token = await make_admin(client)
    jar = cookies(token)
    listing = await client.get("/admin/orders", cookies=jar)
    assert "buyer@it.test" in listing.text

    row = await client.post(
        f"/admin/orders/{order['id']}/advance", cookies=jar, headers={"HX-Request": "true"}
    )
    assert row.status_code == 200
    assert "Shipped" in row.text
