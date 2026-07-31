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
    os.environ.setdefault("OLLAMA_API_KEY", "integration-dummy")
    os.environ.setdefault("SEARCH_INDEX_WORKER_ENABLED", "false")
    if os.environ.get("RELEVANCE_LIVE") != "1":
        os.environ["SMART_SEARCH_ENABLED"] = "false"
        for name in (
            "EMBEDDING_PROVIDER",
            "EMBEDDING_API_KEY",
            "EMBEDDING_FALLBACK_PROVIDER",
            "RERANKER_PROVIDER",
            "RERANKER_API_KEY",
            "RERANKER_FALLBACK_PROVIDER",
            "RERANKER_FALLBACK_API_KEY",
        ):
            os.environ[name] = ""


@pytest.fixture(scope="session")
def _migrated() -> None:
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


_CANDIDATE_TABLES = (
    "ai_chat_messages",
    "ai_chat_sessions",
    "ai_search_events",
    "ai_search_index_jobs",
    "ai_search_documents",
    "ai_search_query_embeddings",
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

    from app.core.index_state import IndexCoverage

    coverage = container.resolve(IndexCoverage)
    coverage.ready = False
    coverage.active_products = 0
    coverage.documents = 0
    yield


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
def embedding(app, monkeypatch):
    from app.application.iservices.iindex_service import IIndexService
    from app.application.iservices.isearch_service import ISearchService
    from app.application.llm import resilient_embedding_client
    from app.application.llm.embedding_providers import EmbeddingProviders
    from app.application.llm.resilient_embedding_client import ResilientEmbeddingClient
    from app.application.services.index_service import IndexService
    from app.application.services.search_service import SearchService
    from app.core.config import Settings
    from app.core.container import container
    from tests.unit.fakes import FakeEmbeddingClient

    monkeypatch.setattr(resilient_embedding_client, "_BACKOFF_SECONDS", (0.0, 0.0))

    def rebind(providers: EmbeddingProviders) -> None:
        container.bind_instance(EmbeddingProviders, providers)
        container.bind(IIndexService, IndexService, singleton=True)
        container.bind(ISearchService, SearchService, singleton=True)

    def resilient(client, slot: str):
        if client is None:
            return None
        return ResilientEmbeddingClient(
            client, container.resolve(Settings), name=f"{slot}:{client.model}"
        )

    def bind(primary=None, fallback=None) -> EmbeddingProviders:
        providers = EmbeddingProviders(
            primary=resilient(primary if primary is not None else FakeEmbeddingClient(), "primary"),
            fallback=resilient(fallback, "fallback"),
        )
        rebind(providers)
        return providers

    yield bind

    rebind(EmbeddingProviders(primary=None))


@pytest.fixture
def smart_search(app):
    from app.core.config import Settings
    from app.core.container import container

    settings = container.resolve(Settings)
    previous = settings.SMART_SEARCH_ENABLED
    settings.SMART_SEARCH_ENABLED = True
    yield settings
    settings.SMART_SEARCH_ENABLED = previous


@pytest.fixture
async def archive_product(app):
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
