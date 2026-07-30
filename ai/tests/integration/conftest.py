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
    # No embedding provider, set rather than defaulted.
    #
    # `Settings` reads the repo-root `.env`, which on a developer machine names a real provider
    # and a real key. Left alone, the suite would reach a live API — different results on a
    # developer machine and in CI, spend on every run, and a rate limit deciding whether tests
    # pass. Clearing them here makes the *absence* of a provider the baseline everywhere, which
    # is also what CI has, and the tests that need a semantic leg bind a FakeEmbeddingClient
    # explicitly so what they exercise is visible in the test rather than in the environment.
    #
    # RELEVANCE_LIVE is the one deliberate exception: `test_search_relevance_live.py` measures
    # the real model and has to be given it. Nothing else in the suite runs under that flag.
    if os.environ.get("RELEVANCE_LIVE") != "1":
        for name in ("EMBEDDING_PROVIDER", "EMBEDDING_API_KEY", "EMBEDDING_FALLBACK_PROVIDER"):
            os.environ[name] = ""


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
    # Not keyed on anything a truncate of the other tables would invalidate, so a row cached by
    # one test is served to the next — which showed up as a test that passed alone and failed in
    # the suite, the worst way to find it.
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
def embedding(app, monkeypatch):
    """Bind a deterministic embedding provider for one test, and take it away afterwards.

    Returns a factory so a test can choose the shape it needs — one provider or two, healthy or
    failing. The default state for the whole suite is *no* provider, so anything exercising the
    semantic path has to say so, and a test that accidentally depends on one fails loudly rather
    than reaching a live API.

    Each fake is wrapped in `ResilientEmbeddingClient` exactly as `registry.configure` wraps a
    real adapter. Binding the bare fake would build a composition that exists in no deployment:
    the timeout, the retry and the circuit breaker would all be missing, and the integration
    suite would be proving the behaviour of something nobody runs.

    Re-binding `IIndexService` and `ISearchService` is what drops the cached singletons: both
    hold their providers from construction, so swapping only `EmbeddingProviders` would leave
    them talking to whatever they were built with. `bind()` clears the singleton as part of its
    contract.
    """
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

    # Retry backoff is real sleeping. Every retryable-failure test would otherwise pay a second
    # per attempt for a delay that is about being kind to a provider, not about correctness.
    monkeypatch.setattr(resilient_embedding_client, "_BACKOFF_SECONDS", (0.0, 0.0))

    def rebind(providers: EmbeddingProviders) -> None:
        container.bind_instance(EmbeddingProviders, providers)
        # Both are singletons and both capture their providers at construction, so swapping only
        # the binding would leave them talking to whatever they were built with. `bind()` drops
        # the cached singleton as part of its contract.
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
    """Turn SMART_SEARCH_ENABLED on for one test and put it back afterwards.

    The flag is off everywhere else, which is the shipped default and the state the rest of the
    suite asserts against. Flipping it per test keeps the two behaviours — semantic search, and
    the honest `feature_disabled` report without it — both covered.
    """
    from app.core.config import Settings
    from app.core.container import container

    settings = container.resolve(Settings)
    previous = settings.SMART_SEARCH_ENABLED
    settings.SMART_SEARCH_ENABLED = True
    yield settings
    settings.SMART_SEARCH_ENABLED = previous


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
