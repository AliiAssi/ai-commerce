from __future__ import annotations

from app.application.events.bus import EventBus
from app.application.events.handlers import register_handlers
from app.application.iservices.ichat_service import IChatService
from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.isearch_service import ISearchService
from app.application.llm.illm_client import ILLMClient
from app.application.llm.ollama_client import OllamaClient
from app.application.llm.resilient_client import ResilientLLMClient
from app.application.search.parser import IntentParser
from app.application.services.chat_service import ChatService
from app.application.services.index_service import IndexService
from app.application.services.search_service import SearchService
from app.application.tools.bootstrap import build_tool_registry
from app.application.tools.registry import ToolRegistry
from app.core.config import Settings
from app.core.container import Container
from app.core.index_state import IndexCoverage
from app.core.prompts import PromptLibrary, load_prompts_or_exit
from app.core.search_aliases import AliasLibrary, load_aliases_or_exit
from app.infrastructure.database.session import create_engine_and_sessionmaker
from app.infrastructure.irepositories.ichat_repository import IChatRepository
from app.infrastructure.irepositories.iorder_read_repository import IOrderReadRepository
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository
from app.infrastructure.irepositories.ireview_read_repository import IReviewReadRepository
from app.infrastructure.irepositories.isearch_index_repository import ISearchIndexRepository
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.repositories.chat_repository import ChatRepository
from app.infrastructure.repositories.order_read_repository import OrderReadRepository
from app.infrastructure.repositories.product_read_repository import ProductReadRepository
from app.infrastructure.repositories.review_read_repository import ReviewReadRepository
from app.infrastructure.repositories.search_index_repository import SearchIndexRepository
from app.infrastructure.repositories.search_repository import (
    SearchCapabilities,
    SearchRepository,
)

_LLM_PROVIDERS: dict[str, type[ILLMClient]] = {
    "ollama": OllamaClient,
}


def configure(container: Container, settings: Settings) -> None:
    engine, session_factory = create_engine_and_sessionmaker(settings)
    container.engine = engine
    container.session_factory = session_factory

    container.bind_instance(Settings, settings)

    bus = EventBus()
    register_handlers(bus)
    container.bind_instance(EventBus, bus)

    container.bind_instance(PromptLibrary, load_prompts_or_exit())

    # The lexicon is immutable once loaded, so the parser built on it is a singleton. Whether
    # it still describes the catalog is a separate question, answered against the database in
    # main.py's lifespan.
    aliases = load_aliases_or_exit()
    container.bind_instance(AliasLibrary, aliases)
    container.bind_instance(IntentParser, IntentParser(aliases))

    container.bind(IProductReadRepository, ProductReadRepository)
    container.bind(IOrderReadRepository, OrderReadRepository)
    container.bind(IReviewReadRepository, ReviewReadRepository)
    # One shared, mutable record of what this database can do. Probed at startup in
    # main.py, and switched off at runtime if the database proves a feature missing.
    container.bind_instance(SearchCapabilities, SearchCapabilities())
    # The same idea for a state that changes while the process runs: whether the document index
    # is populated enough for retrieval to read it (§12 step 3 rather than step 4). Probed at
    # startup and refreshed by every sweep, so no search request has to measure it.
    container.bind_instance(IndexCoverage, IndexCoverage())
    container.bind(ISearchRepository, SearchRepository)
    container.bind(ISearchService, SearchService)

    container.bind(ISearchIndexRepository, SearchIndexRepository)
    # A singleton because its worker id identifies this process's leases, and because the
    # background worker and any CLI drain must be the same instance holding them.
    container.bind(IIndexService, IndexService, singleton=True)

    container.bind(IChatRepository, ChatRepository)

    container.bind_instance(ToolRegistry, build_tool_registry(bus))

    provider = _LLM_PROVIDERS[settings.LLM_PROVIDER]
    container.bind_instance(ILLMClient, ResilientLLMClient(provider(settings), settings))

    container.bind(IChatService, ChatService, singleton=True)
