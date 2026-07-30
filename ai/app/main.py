from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.iservices.iindex_service import IIndexService
from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.services.index_worker import IndexWorker
from app.application.tools.registry import ToolRegistry
from app.core.auth import MCPAuthMiddleware
from app.core.config import Settings, load_settings_or_exit
from app.core.container import container, open_scope
from app.core.logging import RequestContextMiddleware, setup_logging
from app.core.prompts import PromptLibrary
from app.core.registry import configure
from app.core.search_aliases import AliasError, AliasLibrary
from app.core.vector_schema import EMBEDDING_VECTOR_DIMENSIONS
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.repositories.search_repository import SearchCapabilities
from app.presentation.controllers import chat_controller, health_controller, search_controller
from app.presentation.error_handlers import register_exception_handlers
from app.presentation.mcp.server import build_mcp_server

logger = logging.getLogger(__name__)


async def probe_search_capabilities() -> None:
    """Find out at boot which optional database features retrieval can use.

    `pg_trgm` is created by the *web* service's migrations, because the trigram indexes sit on
    web's `products` table. So this service can be pointed at a database that simply does not
    have it yet — and without this check the first shopper to type anything would get a 500
    from `word_similarity` not existing.

    Missing is not fatal. The lexical leg answers on its own; what is lost is the transliterated
    spellings (`rakweh`, `zaatar`) that §7.2 added the trigram leg for. Saying so loudly at boot
    is worth more than failing to start.
    """
    try:
        async with open_scope() as scope:
            detected = await scope.resolve(ISearchRepository).detect_capabilities()
    except SQLAlchemyError as exc:
        logger.warning(
            "search capabilities not probed: database unavailable (%s)", exc.__class__.__name__
        )
        return

    capabilities = container.resolve(SearchCapabilities)
    capabilities.trigram = detected.trigram
    if not capabilities.trigram:
        logger.error(
            "pg_trgm is not installed, so trigram retrieval is disabled: transliterated "
            "spellings such as 'rakweh' will not match. Run the web service's migrations "
            "against this database to install it."
        )


async def probe_index_coverage() -> None:
    """Settle at boot whether retrieval may read this service's document table.

    §12's ladder has two lexical rungs and the difference between them is index coverage, so
    something has to measure it. Doing that per request would put two counts on the hot path
    forever; doing it here and again after every sweep costs nothing and is never more stale
    than the index itself.

    It runs even when the worker is disabled, because the `reindex_catalog` CLI is a legitimate
    way to maintain the index without an in-process worker — §11 requires the claim protocol to
    support exactly that. An unreachable database leaves coverage at its default, which is *not
    ready*: `products.search_vector` is a generated column and can never be empty, so falling
    back to it is always safe, while reading an unfilled document table returns nothing at all.
    """
    try:
        coverage = await container.resolve(IIndexService).refresh_coverage()
    except SQLAlchemyError as exc:
        logger.warning(
            "index coverage not probed: database unavailable (%s)", exc.__class__.__name__
        )
        return
    logger.info(
        "search document coverage: %d/%d active products",
        coverage.documents,
        coverage.active_products,
    )


async def verify_semantic_readiness(settings: Settings) -> None:
    """Check at boot that `SMART_SEARCH_ENABLED` describes something that exists (§18).

    The settings validator can only compare settings to each other. It cannot see whether the
    vector column was ever migrated, or whether an embedding client is actually bound — and the
    version of this check that only asked whether three settings were non-empty stopped guarding
    anything the moment the bake-off filled all three in. The flag could then be switched on with
    no column and no client, and §18's prohibition on shipping lexical-only search under the name
    of semantic search would be one configuration mistake away.

    Fatal only when the flag is on, like `verify_search_lexicon` and for the same reason: this
    process also serves chat and MCP, and refusing to start over a feature nobody is reading yet
    trades a real outage for a hypothetical one. A database that cannot be reached is a different
    condition again and is never fatal — the ordinary API must keep serving (§12), and the next
    boot checks again.
    """
    if not settings.SMART_SEARCH_ENABLED:
        return

    if not container.resolve(EmbeddingProviders).any_configured:
        raise RuntimeError(
            "SMART_SEARCH_ENABLED is on but no embedding client is bound. Set EMBEDDING_PROVIDER "
            "to a known adapter, or turn the flag off."
        )

    try:
        async with open_scope() as scope:
            column = await scope.resolve(AsyncSession).scalar(
                text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid = to_regclass('public.ai_search_documents') "
                    "AND attname = 'embedding' AND NOT attisdropped"
                )
            )
    except SQLAlchemyError as exc:
        logger.warning(
            "semantic readiness not probed: database unavailable (%s)", exc.__class__.__name__
        )
        return

    if column is None:
        raise RuntimeError(
            "SMART_SEARCH_ENABLED is on but ai_search_documents has no embedding column. "
            "Run this service's migrations against this database."
        )
    if column != EMBEDDING_VECTOR_DIMENSIONS:
        # Reachable only by pointing at a database migrated at a different width — the settings
        # validator already refuses a mismatched EMBEDDING_DIMENSIONS.
        raise RuntimeError(
            f"ai_search_documents.embedding is vector({column}) but this build expects "
            f"vector({EMBEDDING_VECTOR_DIMENSIONS}). Re-migrate and re-embed."
        )


async def verify_search_lexicon(settings: Settings) -> None:
    """Check at boot that the alias file still describes the catalog (§6).

    A renamed category or a newly introduced origin breaks nothing loudly: queries that used to
    resolve it simply stop resolving, which reads as a slow relevance regression rather than a
    bug. Checking it at boot is what turns that into a fixable failure.

    How loudly depends on whether the feature is live. With SMART_SEARCH_ENABLED the mismatch
    means search is actively answering wrongly, so the service refuses to start. With the flag
    off — the default, and every deploy before §19's rollout — it is logged instead: this
    process also serves chat and MCP, and taking those down over a lexicon that nothing is
    reading yet trades a real outage for a hypothetical one.

    A database that cannot be reached is a different condition and is never fatal here. The
    ordinary API must keep serving (§12), and the next boot checks again.
    """
    try:
        async with open_scope() as scope:
            terms = await scope.resolve(ISearchRepository).catalog_terms()
    except SQLAlchemyError as exc:
        logger.warning(
            "search lexicon not verified: database unavailable (%s)", exc.__class__.__name__
        )
        return
    if not terms.category_slugs:
        logger.warning("search lexicon not verified: the catalog is empty")
        return
    try:
        container.resolve(AliasLibrary).validate_against_catalog(
            category_slugs=terms.category_slugs, origins=terms.origins
        )
    except AliasError:
        if settings.SMART_SEARCH_ENABLED:
            raise
        logger.exception("search lexicon is stale; smart search is disabled so startup continues")


def create_app() -> FastAPI:
    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)

    mcp = build_mcp_server(
        container.resolve(ToolRegistry), container.resolve(PromptLibrary), settings
    )

    worker = IndexWorker(container.resolve(IIndexService), settings)

    # Must run for the whole app lifetime even in stateless mode.
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await probe_search_capabilities()
        await probe_index_coverage()
        await verify_semantic_readiness(settings)
        await verify_search_lexicon(settings)
        # §11 puts the worker in the serving process, so indexing needs no second host. The
        # flag exists for the deployments that drive it from the CLI instead, and for tests,
        # where a background task racing a truncate would make every assertion a coin toss.
        if settings.SEARCH_INDEX_WORKER_ENABLED:
            worker.start()
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            # Uvicorn turns SIGTERM into this shutdown, so stopping here is §11 rule 8. The
            # finally matters: an exception on the way out must still release the leases,
            # otherwise the next deploy waits out a lease it could have had back immediately.
            await worker.stop()
            if container.engine is not None:
                await container.engine.dispose()

    app = FastAPI(title="BEIT", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_controller.router)
    app.include_router(chat_controller.router)
    app.include_router(search_controller.router)

    app.mount("/mcp", MCPAuthMiddleware(mcp.streamable_http_app(), settings))
    return app


app = create_app()
