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
from app.application.rerank.hf_reranker import HuggingFaceReranker
from app.application.rerank.ireranker import IReranker, PassthroughReranker
from app.application.rerank.openrouter_reranker import OpenRouterReranker
from app.application.rerank.reranker_chain import RerankerChain
from app.application.rerank.resilient_reranker import ResilientReranker
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

_EMBEDDING_PROVIDERS: dict[str, type[IEmbeddingClient]] = {
    "gemini": GeminiEmbeddingClient,
    "openrouter": OpenAICompatibleEmbeddingClient,
}

_RERANKERS: dict[str, type[IReranker]] = {
    "openrouter": OpenRouterReranker,
    "huggingface": HuggingFaceReranker,
}


def _build_embedding_providers(settings: Settings) -> EmbeddingProviders:
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


def _build_reranker(settings: Settings) -> IReranker:
    if not settings.RERANKER_PROVIDER:
        return PassthroughReranker()

    def build(provider: str, host: str, api_key: str, model: str, *, slot: str) -> IReranker:
        try:
            adapter = _RERANKERS[provider]
        except KeyError:
            raise ValueError(
                f"Unknown {slot} reranker provider {provider!r}. "
                f"Known adapters: {', '.join(sorted(_RERANKERS))}."
            ) from None
        scoped = settings.model_copy(
            update={
                "RERANKER_PROVIDER": provider,
                "RERANKER_HOST": host,
                "RERANKER_API_KEY": api_key,
                "RERANKER_MODEL": model,
            }
        )
        return ResilientReranker(adapter(scoped), settings, name=f"{slot}:{provider}:{model}")

    primary = build(
        settings.RERANKER_PROVIDER,
        settings.RERANKER_HOST,
        settings.RERANKER_API_KEY,
        settings.RERANKER_MODEL,
        slot="primary",
    )
    if not settings.RERANKER_FALLBACK_PROVIDER:
        return primary
    fallback = build(
        settings.RERANKER_FALLBACK_PROVIDER,
        settings.RERANKER_FALLBACK_HOST,
        settings.RERANKER_FALLBACK_API_KEY,
        settings.RERANKER_FALLBACK_MODEL,
        slot="fallback",
    )
    return RerankerChain(primary, fallback)


def configure(container: Container, settings: Settings) -> None:
    engine, session_factory = create_engine_and_sessionmaker(settings)
    container.engine = engine
    container.session_factory = session_factory

    container.bind_instance(Settings, settings)

    bus = EventBus()
    register_handlers(bus)
    container.bind_instance(EventBus, bus)

    container.bind_instance(PromptLibrary, load_prompts_or_exit())

    aliases = load_aliases_or_exit()
    container.bind_instance(AliasLibrary, aliases)
    container.bind_instance(IntentParser, IntentParser(aliases))

    container.bind(IProductReadRepository, ProductReadRepository)
    container.bind(IOrderReadRepository, OrderReadRepository)
    container.bind(IReviewReadRepository, ReviewReadRepository)
    container.bind_instance(SearchCapabilities, SearchCapabilities())
    container.bind_instance(IndexCoverage, IndexCoverage())
    container.bind_instance(EmbeddingProviders, _build_embedding_providers(settings))
    container.bind(ISearchRepository, SearchRepository)
    container.bind_instance(IReranker, _build_reranker(settings))
    container.bind(ISearchService, SearchService, singleton=True)

    container.bind(ISearchIndexRepository, SearchIndexRepository)
    container.bind(IIndexService, IndexService, singleton=True)

    container.bind_instance(RelevanceCorpus, load_corpus_or_exit())
    container.bind(IRelevanceService, RelevanceService, singleton=True)

    container.bind(IChatRepository, ChatRepository)

    container.bind_instance(ToolRegistry, build_tool_registry(bus))

    provider = _LLM_PROVIDERS[settings.LLM_PROVIDER]
    container.bind_instance(ILLMClient, ResilientLLMClient(provider(settings), settings))

    container.bind(IChatService, ChatService, singleton=True)
