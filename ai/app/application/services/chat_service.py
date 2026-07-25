from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from app.application.dtos.chat_dto import ChatMessageDTO, ChatSessionDTO, ChatStreamEventDTO
from app.application.dtos.tool_dto import ToolContext
from app.application.events.bus import EventBus
from app.application.events.definitions import ChatTurnCompleted
from app.application.iservices.ichat_service import IChatService
from app.application.llm.illm_client import ILLMClient
from app.application.llm.llm_dtos import LLMMessageDTO, LLMToolCallDTO
from app.application.tools.registry import ScopeFactory, ToolRegistry
from app.core.config import Settings
from app.core.container import open_scope
from app.core.exceptions import (
    AgentLoopLimitError,
    LLMUnavailableError,
    SessionNotFoundError,
    ToolExecutionError,
)
from app.core.prompts import PromptLibrary
from app.infrastructure.irepositories.ichat_repository import IChatRepository

logger = logging.getLogger(__name__)


# Raised internally when a session has hit its message cap.
class _SessionFull(Exception):
    pass


# Case/whitespace-insensitive email match; None means guest.
def _same_identity(a: str | None, b: str | None) -> bool:
    return (a.strip().lower() if a else None) == (b.strip().lower() if b else None)


# The agent loop: system prompt + history + user turn, then the LLM streams tokens and may
# call tools until it answers (capped by MAX_TOOL_ITERATIONS). Singleton — opens its own short
# DB scopes for chat history instead of holding one across an LLM turn.
class ChatService(IChatService):
    def __init__(
        self,
        llm: ILLMClient,
        registry: ToolRegistry,
        prompts: PromptLibrary,
        settings: Settings,
        events: EventBus,
        scope_factory: ScopeFactory = open_scope,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._prompts = prompts
        self._settings = settings
        self._events = events
        self._scope_factory = scope_factory

    async def resolve_session(
        self, session_id: uuid.UUID | None, user_email: str | None
    ) -> ChatSessionDTO:
        async with self._scope_factory() as scope:
            repo = scope.resolve(IChatRepository)
            if session_id is None:
                return await repo.create_session(user_email)
            existing = await repo.get_session(session_id)
            if existing is None:
                raise SessionNotFoundError(f"no chat session {session_id}")
            if not _same_identity(existing.user_email, user_email):
                return await repo.create_session(user_email)
            return existing

    async def stream_reply(
        self, session: ChatSessionDTO, message: str
    ) -> AsyncIterator[ChatStreamEventDTO]:
        try:
            history = await self._load_history(session.id)
        except _SessionFull:
            yield ChatStreamEventDTO(
                type="error", message=self._prompts.render("chat.session_limit_reply")
            )
            return

        context = ToolContext(source="chat", user_email=session.user_email)
        llm_messages = self._initial_messages(history, message)
        tools = self._registry.ollama_tools()

        answer = ""
        calls_made: list[dict] = []
        prompt_tokens = 0
        completion_tokens = 0

        try:
            for _ in range(self._settings.MAX_TOOL_ITERATIONS + 1):
                text_parts: list[str] = []
                tool_calls: list[LLMToolCallDTO] = []
                async for event in self._llm.stream(llm_messages, tools):
                    if event.type == "token" and event.text:
                        text_parts.append(event.text)
                        yield ChatStreamEventDTO(type="token", text=event.text)
                    elif event.type == "tool_call" and event.tool_call:
                        tool_calls.append(event.tool_call)
                    elif event.type == "done" and event.usage:
                        prompt_tokens += event.usage.prompt_tokens
                        completion_tokens += event.usage.completion_tokens

                if not tool_calls:
                    answer = "".join(text_parts)
                    break

                llm_messages.append(
                    LLMMessageDTO(
                        role="assistant", content="".join(text_parts), tool_calls=tool_calls
                    )
                )
                for call in tool_calls:
                    calls_made.append({"name": call.name, "arguments": call.arguments})
                    yield ChatStreamEventDTO(type="tool", name=call.name)
                    result = await self._execute_tool(call, context)
                    llm_messages.append(
                        LLMMessageDTO(role="tool", content=result, tool_name=call.name)
                    )
            else:
                raise AgentLoopLimitError("exceeded MAX_TOOL_ITERATIONS")
        except LLMUnavailableError:
            yield ChatStreamEventDTO(
                type="error", message=self._prompts.render("errors.llm_unavailable")
            )
            return
        except AgentLoopLimitError:
            yield ChatStreamEventDTO(
                type="error", message="Sorry — I couldn't work that out. Please try rephrasing."
            )
            return

        await self._persist(session.id, message, answer, calls_made)
        self._events.publish(
            ChatTurnCompleted(str(session.id), len(calls_made), prompt_tokens, completion_tokens)
        )
        yield ChatStreamEventDTO(type="done", session_id=session.id)

    async def _load_history(self, session_id: uuid.UUID) -> list[ChatMessageDTO]:
        async with self._scope_factory() as scope:
            repo = scope.resolve(IChatRepository)
            if await repo.count_messages(session_id) >= self._settings.MAX_MESSAGES_PER_SESSION:
                raise _SessionFull
            return await repo.list_messages(session_id)

    def _initial_messages(self, history: list[ChatMessageDTO], message: str) -> list[LLMMessageDTO]:
        messages = [
            LLMMessageDTO(
                role="system",
                content=self._prompts.render("chat.system", store_name=self._settings.STORE_NAME),
            )
        ]
        for stored in history:
            messages.append(LLMMessageDTO(role=stored.role, content=stored.content))
        messages.append(LLMMessageDTO(role="user", content=message))
        return messages

    # A failed tool's error is fed back to the LLM as its result so it can recover.
    async def _execute_tool(self, call: LLMToolCallDTO, context: ToolContext) -> str:
        try:
            result = await self._registry.execute(call.name, call.arguments, context)
        except ToolExecutionError as exc:
            result = {"error": exc.message}
        return json.dumps(result)

    async def _persist(
        self, session_id: uuid.UUID, user_message: str, answer: str, calls_made: list[dict]
    ) -> None:
        async with self._scope_factory() as scope:
            repo = scope.resolve(IChatRepository)
            await repo.append_messages(
                session_id,
                [
                    ChatMessageDTO(role="user", content=user_message),
                    ChatMessageDTO(role="assistant", content=answer, tool_calls=calls_made or None),
                ],
            )
