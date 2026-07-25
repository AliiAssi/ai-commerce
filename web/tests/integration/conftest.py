from __future__ import annotations

import os
import subprocess
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
WEB_DIR = Path(__file__).resolve().parents[2]

if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ.setdefault("JWT_SECRET", "integration-test-secret-0123456789ab")
    # enable the AI proxy so /api/v1/ai/chat is exercised (a fake gateway is bound in-test)
    os.environ.setdefault("AI_SERVICE_URL", "http://ai.test")
    os.environ.setdefault("INTERNAL_API_KEY", "integration-internal-key")

DEFAULT_PASSWORD = "Password#123"


# register a fresh user through the real endpoint and hand back the token payload
async def register_user(
    client: httpx.AsyncClient, email: str, password: str = DEFAULT_PASSWORD
) -> dict:
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


# bearer header from a token payload
def auth_headers(token_payload: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_payload['access_token']}"}


# register, promote to admin in the db, re-login so the token carries the admin role
async def make_admin(client: httpx.AsyncClient, email: str = "admin@it.test") -> dict:
    from sqlalchemy import text

    from app.core.container import container

    await register_user(client, email)
    assert container.session_factory is not None
    async with container.session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email}
        )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()


# run migrations once for the whole session against the test database
@pytest.fixture(scope="session")
def _migrated() -> None:
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=WEB_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
    )


# one ASGI client (and thus one app + engine) for the whole session
@pytest.fixture(scope="session")
async def client(_migrated):
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    from app.core.container import container

    if container.engine is not None:
        await container.engine.dispose()


# every test starts from empty tables
@pytest.fixture(autouse=True)
async def _clean(client):
    from sqlalchemy import text

    from app.core.container import container

    assert container.session_factory is not None
    async with container.session_factory() as session, session.begin():
        await session.execute(
            text(
                "TRUNCATE reviews, order_items, orders, cart_items, carts, "
                "products, categories, users RESTART IDENTITY CASCADE"
            )
        )
    yield


# three products in one category: plenty of stock, low stock, and out of stock
@pytest.fixture
async def catalog(client, _clean) -> dict:
    from app.application.dtos.product_dto import ProductCreateDTO
    from app.core.container import container
    from app.infrastructure.repositories.product_repository import ProductRepository

    assert container.session_factory is not None
    async with container.session_factory() as session, session.begin():
        repo = ProductRepository(session)
        category = await repo.create_category("Gear", "gear")
        alpha = await repo.create(
            ProductCreateDTO(
                name="Alpha Tent",
                description="A sturdy waterproof two-person tent for camping trips",
                price=Decimal("100.00"),
                stock=5,
                category_id=category.id,
            )
        )
        beta = await repo.create(
            ProductCreateDTO(
                name="Beta Stove",
                description="Compact camping stove with piezo ignition",
                price=Decimal("25.50"),
                stock=2,
                category_id=category.id,
            )
        )
        gamma = await repo.create(
            ProductCreateDTO(
                name="Gamma Lantern",
                description="Rechargeable LED lantern for tents and power cuts",
                price=Decimal("15.00"),
                stock=0,
                category_id=category.id,
            )
        )
    return {"category": category, "alpha": alpha, "beta": beta, "gamma": gamma}
