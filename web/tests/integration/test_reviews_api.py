from __future__ import annotations

import os

import pytest

from tests.integration.conftest import auth_headers, register_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


# buy one unit of a product so the user becomes a verified purchaser
async def _buy(client, headers, product_id: int) -> None:
    response = await client.post(
        "/api/v1/cart/items", json={"product_id": product_id}, headers=headers
    )
    assert response.status_code == 201
    response = await client.post("/api/v1/checkout", headers=headers)
    assert response.status_code == 201


async def test_non_purchaser_403(client, catalog):
    headers = auth_headers(await register_user(client, "reader@it.test"))
    response = await client.post(
        f"/api/v1/products/{catalog['alpha'].id}/reviews",
        json={"rating": 5, "text": "never bought it though"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_purchaser_review_updates_rating(client, catalog):
    alpha = catalog["alpha"]
    headers = auth_headers(await register_user(client, "buyer@it.test"))
    await _buy(client, headers, alpha.id)

    response = await client.post(
        f"/api/v1/products/{alpha.id}/reviews",
        json={"rating": 4, "text": "kept us dry through a storm"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["user_email"] == "buyer@it.test"

    product = (await client.get(f"/api/v1/products/{alpha.id}")).json()
    assert product["rating_avg"] == "4.00"
    assert product["review_count"] == 1

    reviews = (await client.get(f"/api/v1/products/{alpha.id}/reviews")).json()
    assert len(reviews) == 1


async def test_duplicate_review_409(client, catalog):
    alpha = catalog["alpha"]
    headers = auth_headers(await register_user(client, "buyer@it.test"))
    await _buy(client, headers, alpha.id)

    body = {"rating": 4, "text": "kept us dry through a storm"}
    await client.post(f"/api/v1/products/{alpha.id}/reviews", json=body, headers=headers)
    response = await client.post(f"/api/v1/products/{alpha.id}/reviews", json=body, headers=headers)
    assert response.status_code == 409


async def test_invalid_rating_422(client, catalog):
    headers = auth_headers(await register_user(client, "buyer@it.test"))
    response = await client.post(
        f"/api/v1/products/{catalog['alpha'].id}/reviews",
        json={"rating": 6, "text": "off the scale"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_cancelled_order_does_not_verify(client, catalog):
    alpha = catalog["alpha"]
    headers = auth_headers(await register_user(client, "flaky@it.test"))
    await client.post("/api/v1/cart/items", json={"product_id": alpha.id}, headers=headers)
    order = (await client.post("/api/v1/checkout", headers=headers)).json()
    await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers)

    response = await client.post(
        f"/api/v1/products/{alpha.id}/reviews",
        json={"rating": 5, "text": "cancelled but reviewing anyway"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_eligibility_answers_a_signed_out_caller_with_200(client, catalog):
    response = await client.get(f"/api/v1/products/{catalog['alpha'].id}/reviews/eligibility")
    assert response.status_code == 200
    assert response.json() == {"can_review": False, "reason": "not_authenticated", "review": None}


async def test_eligibility_walks_a_shopper_through_every_state(client, catalog):
    alpha = catalog["alpha"]
    headers = auth_headers(await register_user(client, "eligible@it.test"))
    url = f"/api/v1/products/{alpha.id}/reviews/eligibility"

    body = (await client.get(url, headers=headers)).json()
    assert body["can_review"] is False
    assert body["reason"] == "not_purchased"

    await _buy(client, headers, alpha.id)
    body = (await client.get(url, headers=headers)).json()
    assert body["can_review"] is True
    assert body["reason"] is None

    await client.post(
        f"/api/v1/products/{alpha.id}/reviews",
        json={"rating": 5, "text": "worth every cent"},
        headers=headers,
    )
    body = (await client.get(url, headers=headers)).json()
    assert body["can_review"] is False
    assert body["reason"] == "already_reviewed"
    assert body["review"]["rating"] == 5
    assert body["review"]["text"] == "worth every cent"


async def test_eligibility_404s_on_an_unknown_product(client):
    response = await client.get("/api/v1/products/999999/reviews/eligibility")
    assert response.status_code == 404
