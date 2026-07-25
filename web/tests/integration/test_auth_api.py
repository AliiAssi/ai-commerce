from __future__ import annotations

import os

import pytest

from tests.integration.conftest import auth_headers, register_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


async def test_register_then_me(client):
    token = await register_user(client, "alice@it.test")
    assert token["token_type"] == "bearer"
    assert token["user"]["role"] == "customer"

    response = await client.get("/api/v1/me", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json()["email"] == "alice@it.test"


async def test_register_duplicate_email_409(client):
    await register_user(client, "alice@it.test")
    response = await client.post(
        "/api/v1/auth/register", json={"email": "ALICE@it.test", "password": "Password#123"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_login_wrong_password_401(client):
    await register_user(client, "alice@it.test")
    response = await client.post(
        "/api/v1/auth/login", json={"email": "alice@it.test", "password": "nope-nope"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_requires_token(client):
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


async def test_short_password_422(client):
    response = await client.post(
        "/api/v1/auth/register", json={"email": "bob@it.test", "password": "short"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
