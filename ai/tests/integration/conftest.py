from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
AI_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = AI_DIR.parent / "web"

MCP_BEARER_TOKEN = "integration-mcp-bearer-token"
INTERNAL_API_KEY = "integration-internal-key-value"

if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ.setdefault("INTERNAL_API_KEY", INTERNAL_API_KEY)
    os.environ.setdefault("MCP_BEARER_TOKEN", MCP_BEARER_TOKEN)
    os.environ.setdefault("OLLAMA_API_KEY", "integration-dummy")  # never called in tests


# store schema is owned by web; ai_* tables by this service. Run both migration sets
# against the shared test database (they use separate alembic version tables).
@pytest.fixture(scope="session")
def _migrated() -> None:
    # web's Settings requires JWT_SECRET even just to run migrations; supply a throwaway
    web_env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL, "JWT_SECRET": "x" * 32}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=WEB_DIR, env=web_env
    )
    if (AI_DIR / "alembic.ini").exists():
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            check=True,
            cwd=AI_DIR,
            env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        )


# one lifespan-managed app (so the MCP session manager runs) + engine for the whole session
@pytest.fixture(scope="session")
async def app(_migrated):
    from asgi_lifespan import LifespanManager

    from app.main import app as fastapi_app

    async with LifespanManager(fastapi_app):
        yield fastapi_app

    from app.core.container import container

    if container.engine is not None:
        await container.engine.dispose()


@pytest.fixture(scope="session")
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# every test starts from empty tables; only truncate what exists (ai_* arrive in WP4)
_CANDIDATE_TABLES = (
    "ai_chat_messages",
    "ai_chat_sessions",
    "reviews",
    "order_items",
    "orders",
    "cart_items",
    "carts",
    "products",
    "categories",
    "users",
)


@pytest.fixture(autouse=True)
async def _clean(app):
    from sqlalchemy import text

    from app.core.container import container

    assert container.session_factory is not None
    async with container.session_factory() as session, session.begin():
        present = set(
            (
                await session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            )
            .scalars()
            .all()
        )
        targets = [t for t in _CANDIDATE_TABLES if t in present]
        if targets:
            await session.execute(text(f"TRUNCATE {', '.join(targets)} RESTART IDENTITY CASCADE"))
    yield


# seed a small catalog straight into web-owned tables (test-only writes are fine)
@pytest.fixture
async def catalog(app) -> dict:
    from sqlalchemy import insert

    from app.core.container import container
    from app.infrastructure.database.store_tables import categories, products

    now = datetime.now(UTC)
    assert container.session_factory is not None
    async with container.session_factory() as session, session.begin():
        gear = (
            await session.execute(
                insert(categories).values(name="Gear", slug="gear").returning(categories.c.id)
            )
        ).scalar_one()
        await session.execute(
            insert(products),
            [
                {
                    "category_id": gear,
                    "name": "Alpha Tent",
                    "description": "A sturdy waterproof two-person tent for camping trips",
                    "price": Decimal("100.00"),
                    "stock": 5,
                    "image_url": None,
                    "rating_avg": Decimal("4.50"),
                    "review_count": 8,
                    "is_archived": False,
                    "created_at": now,
                },
                {
                    "category_id": gear,
                    "name": "Beta Stove",
                    "description": "Compact camping stove with piezo ignition",
                    "price": Decimal("25.50"),
                    "stock": 0,
                    "image_url": None,
                    "rating_avg": Decimal("4.90"),
                    "review_count": 3,
                    "is_archived": False,
                    "created_at": now,
                },
            ],
        )
    return {"category_slug": "gear"}
