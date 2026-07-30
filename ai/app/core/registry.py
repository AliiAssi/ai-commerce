from __future__ import annotations

from app.application.events.bus import EventBus
from app.application.events.handlers import register_handlers
from app.application.iservices.ichat_service import IChatService
from app.application.iservices.iindex_service import IIndexService
from app.application.iservices.irelevance_service import IRelevanceService
from app.application.iservices.isearch_service import ISearchService
from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.llm.gemini_embedding_client import GeminiEmbeddingClient
from app.application.llm.iembedding_client import IEmbeddingClient
from app.application.llm.illm_client import ILLMClient
from app.application.llm.ollama_client import OllamaClient
from app.application.llm.openai_embedding_client import OpenAICompatibleEmbeddingClient
from app.application.llm.resilient_client import ResilientLLMClient
from app.application.llm.resilient_embedding_client import ResilientEmbeddingClient
from app.application.rerank.ireranker import IReranker, PassthroughReranker
from app.application.search.parser import IntentParser
from app.application.services.chat_service import ChatService
from app.application.services.index_service import IndexService
from app.application.services.relevance_service import RelevanceService
from app.application.services.search_service import SearchService
from app.application.tools.bootstrap import build_tool_registry
from app.application.tools.registry import ToolRegistry
from app.core.config import Settings
from app.core.container import Container
from app.core.index_state import IndexCoverage
from app.core.prompts import PromptLibrary, load_prompts_or_exit
from app.core.relevance import RelevanceCorpus, load_corpus_or_exit
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

# Adapter names, not URLs. `openrouter` is the OpenAI-compatible shape and serves any host that
# speaks /v1/embeddings; the name records which one was measured.
_EMBEDDING_PROVIDERS: dict[str, type[IEmbeddingClient]] = {
    "gemini": GeminiEmbeddingClient,
    "openrouter": OpenAICompatibleEmbeddingClient,
}


def _build_embedding_providers(settings: Settings) -> EmbeddingProviders:
    """Both providers, each wrapped in its own breaker, or nothing at all.

    Nothing at all is the ordinary case: the flag is off by default and this service also serves
    chat and MCP, so an absent embedding configuration must not stop it starting. What must not
    happen quietly is an embedding configuration that names an adapter nobody wrote — that is a
    typo whose only symptom would be a semantic leg that never runs.
    """
    if not settings.EMBEDDING_PROVIDER:
        return EmbeddingProviders(primary=None)

    def build(provider: str, host: str, api_key: str, model: str, *, slot: str) -> IEmbeddingClient:
        try:
            adapter = _EMBEDDING_PROVIDERS[provider]
        except KeyError:
            raise ValueError(
                f"Unknown {slot} embedding provider {provider!r}. "
                f"Known adapters: {', '.join(sorted(_EMBEDDING_PROVIDERS))}."
            ) from None
        # The adapters read the embedding settings off the whole Settings object, so the fallback
        # gets a copy with its own credentials — the same shape the bake-off used to build five
        # candidates from one configuration. Dimensions are deliberately not overridden: both
        # columns are vector(EMBEDDING_DIMENSIONS) and a second width could not be stored.
        scoped = settings.model_copy(
            update={
                "EMBEDDING_PROVIDER": provider,
                "EMBEDDING_HOST": host,
                "EMBEDDING_API_KEY": api_key,
                "EMBEDDING_MODEL": model,
            }
        )
        return ResilientEmbeddingClient(adapter(scoped), settings, name=f"{slot}:{model}")

    primary = build(
        settings.EMBEDDING_PROVIDER,
        settings.EMBEDDING_HOST,
        settings.EMBEDDING_API_KEY,
        settings.EMBEDDING_MODEL,
        slot="primary",
    )
    fallback = None
    if settings.EMBEDDING_FALLBACK_PROVIDER:
        fallback = build(
            settings.EMBEDDING_FALLBACK_PROVIDER,
            settings.EMBEDDING_FALLBACK_HOST,
            settings.EMBEDDING_FALLBACK_API_KEY,
            settings.EMBEDDING_FALLBACK_MODEL,
            slot="fallback",
        )
    return EmbeddingProviders(primary=primary, fallback=fallback)


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
    # Both embedding providers, each behind its own circuit breaker (§12 requires them to be
    # independent). One instance for the process, because a breaker that reset per request would
    # be no breaker at all.
    container.bind_instance(EmbeddingProviders, _build_embedding_providers(settings))
    container.bind(ISearchRepository, SearchRepository)
    # §12 step 2's fallback, available before the thing it is a fallback for. Phase 7 replaces
    # this binding with a real reranker and the degraded path is already the default.
    container.bind_instance(IReranker, PassthroughReranker())
    # A singleton, because it holds no session: it opens its own short scopes around the
    # embedding call rather than inheriting a request-long transaction (§11 rule 9).
    container.bind(ISearchService, SearchService, singleton=True)

    container.bind(ISearchIndexRepository, SearchIndexRepository)
    # A singleton because its worker id identifies this process's leases, and because the
    # background worker and any CLI drain must be the same instance holding them.
    container.bind(IIndexService, IndexService, singleton=True)

    # The §15 corpus is immutable once loaded, like the alias lexicon. It is bound rather than
    # read by the scorer so a malformed corpus fails at boot with a readable message instead of
    # halfway through a bake-off run.
    container.bind_instance(RelevanceCorpus, load_corpus_or_exit())
    container.bind(IRelevanceService, RelevanceService, singleton=True)

    container.bind(IChatRepository, ChatRepository)

    container.bind_instance(ToolRegistry, build_tool_registry(bus))

    provider = _LLM_PROVIDERS[settings.LLM_PROVIDER]
    container.bind_instance(ILLMClient, ResilientLLMClient(provider(settings), settings))

    container.bind(IChatService, ChatService, singleton=True)
