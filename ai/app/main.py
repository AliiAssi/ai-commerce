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
        raise RuntimeError(
            f"ai_search_documents.embedding is vector({column}) but this build expects "
            f"vector({EMBEDDING_VECTOR_DIMENSIONS}). Re-migrate and re-embed."
        )


async def verify_search_lexicon(settings: Settings) -> None:
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

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await probe_search_capabilities()
        await probe_index_coverage()
        await verify_semantic_readiness(settings)
        await verify_search_lexicon(settings)
        if settings.SEARCH_INDEX_WORKER_ENABLED:
            worker.start()
        try:
            async with mcp.session_manager.run():
                yield
        finally:
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
