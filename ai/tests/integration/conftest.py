from __future__ import annotations

import importlib.util
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
    # One lifespan covers the whole session (see the `app` fixture), so a background index
    # worker would run for the whole suite — sweeping, claiming and writing against tables the
    # autouse `_clean` truncates between every test. Every assertion would become a race. The
    # indexing tests drive IndexService directly instead, which is the stricter check anyway:
    # it pins the units of work rather than whatever the loop happened to get through.
    os.environ.setdefault("SEARCH_INDEX_WORKER_ENABLED", "false")


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
    "ai_search_events",
    "ai_search_index_jobs",
    "ai_search_documents",
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

    # The coverage gate is process-wide mutable state that outlives the truncate above, so a
    # test that populated the index would otherwise leave retrieval pointed at a document table
    # the next test has just emptied. Reset it with the tables it describes.
    from app.core.index_state import IndexCoverage

    coverage = container.resolve(IndexCoverage)
    coverage.ready = False
    coverage.active_products = 0
    coverage.documents = 0
    yield


# The real BEIT catalog, loaded from web's seed data by path.
#
# Search relevance is a property of *this* catalog — the transliterated names, the two spellings
# of Tripoli, the sold-out sumac — so a two-product stand-in would let every retrieval test pass
# while proving nothing. Importing the module by path rather than copying 46 products keeps the
# two in step; the conftest already reaches into web's directory to run its migrations.
def _seed_data():
    spec = importlib.util.spec_from_file_location(
        "beit_seed_data", WEB_DIR / "app" / "application" / "jobs" / "seed_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def seed_data():
    return _seed_data()


@pytest.fixture
async def beit_catalog(app, seed_data) -> dict[int, str]:
    """Seed the full catalog and return {product_id: name}."""
    from sqlalchemy import insert, select

    from app.core.container import container
    from app.infrastructure.database.store_tables import categories, products

    now = datetime.now(UTC)
    assert container.session_factory is not None
    async with container.session_factory() as session, session.begin():
        await session.execute(
            insert(categories),
            [{"name": name, "slug": slug} for name, slug in seed_data.CATEGORIES],
        )
        by_slug = {
            row.slug: row.id
            for row in (await session.execute(select(categories.c.id, categories.c.slug))).all()
        }
        await session.execute(
            insert(products),
            [
                {
                    "category_id": by_slug[slug],
                    "name": name,
                    "description": description,
                    "origin": origin,
                    "price": Decimal(price),
                    "stock": stock,
                    "image_url": image_url,
                    "rating_avg": Decimal("4.50"),
                    "review_count": 5,
                    "is_archived": False,
                    "created_at": now,
                }
                for slug, name, origin, price, stock, description, image_url in seed_data.PRODUCTS
            ],
        )
        rows = (await session.execute(select(products.c.id, products.c.name))).all()
    return {row.id: row.name for row in rows}


@pytest.fixture
async def archive_product(app):
    """Archive one product by name, so a test can prove it leaves the results."""
    from sqlalchemy import update

    from app.core.container import container
    from app.infrastructure.database.store_tables import products

    async def archive(name: str) -> None:
        assert container.session_factory is not None
        async with container.session_factory() as session, session.begin():
            await session.execute(
                update(products).where(products.c.name == name).values(is_archived=True)
            )

    return archive


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
