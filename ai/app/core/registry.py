from __future__ import annotations

from app.application.events.bus import EventBus
from app.application.events.handlers import register_handlers
from app.application.iservices.ichat_service import IChatService
from app.application.llm.illm_client import ILLMClient
from app.application.llm.ollama_client import OllamaClient
from app.application.llm.resilient_client import ResilientLLMClient
from app.application.services.chat_service import ChatService
from app.application.tools.bootstrap import build_tool_registry
from app.application.tools.registry import ToolRegistry
from app.core.config import Settings
from app.core.container import Container
from app.core.prompts import PromptLibrary, load_prompts_or_exit
from app.infrastructure.database.session import create_engine_and_sessionmaker
from app.infrastructure.irepositories.ichat_repository import IChatRepository
from app.infrastructure.irepositories.iorder_read_repository import IOrderReadRepository
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository
from app.infrastructure.irepositories.ireview_read_repository import IReviewReadRepository
from app.infrastructure.repositories.chat_repository import ChatRepository
from app.infrastructure.repositories.order_read_repository import OrderReadRepository
from app.infrastructure.repositories.product_read_repository import ProductReadRepository
from app.infrastructure.repositories.review_read_repository import ReviewReadRepository

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

    container.bind(IProductReadRepository, ProductReadRepository)
    container.bind(IOrderReadRepository, OrderReadRepository)
    container.bind(IReviewReadRepository, ReviewReadRepository)

    container.bind(IChatRepository, ChatRepository)

    container.bind_instance(ToolRegistry, build_tool_registry(bus))

    provider = _LLM_PROVIDERS[settings.LLM_PROVIDER]
    container.bind_instance(ILLMClient, ResilientLLMClient(provider(settings), settings))

    container.bind(IChatService, ChatService, singleton=True)
