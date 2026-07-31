from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.application.llm.illm_client import ILLMClient
from app.application.llm.llm_dtos import LLMMessageDTO, LLMReplyDTO, LLMStreamEventDTO
from app.application.llm.resilient_client import ResilientLLMClient
from app.core.config import Settings
from app.core.exceptions import LLMUnavailableError

MESSAGES = [LLMMessageDTO(role="user", content="hi")]


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://u:p@h/db",
        INTERNAL_API_KEY="x" * 16,
        MCP_BEARER_TOKEN="y" * 16,
        OLLAMA_API_KEY="test-key",
        LLM_TIMEOUT_SECONDS=5,
    )


class ScriptedInner(ILLMClient):
    def __init__(self, chat_outcomes=None, stream_outcomes=None) -> None:
        self._chat = list(chat_outcomes or [])
        self._stream = list(stream_outcomes or [])
        self.chat_attempts = 0
        self.stream_attempts = 0

    async def chat(self, messages, tools=None) -> LLMReplyDTO:
        self.chat_attempts += 1
        outcome = self._chat.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def stream(self, messages, tools=None) -> AsyncIterator[LLMStreamEventDTO]:
        self.stream_attempts += 1
        outcome = self._stream.pop(0)
        for item in outcome:
            if isinstance(item, Exception):
                raise item
            yield item


def _resilient(inner: ILLMClient) -> ResilientLLMClient:
    return ResilientLLMClient(inner, _settings())


async def test_chat_retries_then_succeeds() -> None:
    reply = LLMReplyDTO(content="ok")
    inner = ScriptedInner(chat_outcomes=[LLMUnavailableError("503", retryable=True), reply])
    result = await _resilient(inner).chat(MESSAGES)
    assert result.content == "ok"
    assert inner.chat_attempts == 2


async def test_chat_does_not_retry_fatal() -> None:
    inner = ScriptedInner(chat_outcomes=[LLMUnavailableError("bad key", retryable=False)])
    with pytest.raises(LLMUnavailableError):
        await _resilient(inner).chat(MESSAGES)
    assert inner.chat_attempts == 1


async def test_chat_gives_up_after_max_attempts() -> None:
    inner = ScriptedInner(chat_outcomes=[LLMUnavailableError("503", retryable=True)] * 3)
    with pytest.raises(LLMUnavailableError):
        await _resilient(inner).chat(MESSAGES)
    assert inner.chat_attempts == 3


async def test_stream_retries_before_first_event() -> None:
    inner = ScriptedInner(
        stream_outcomes=[
            [LLMUnavailableError("503", retryable=True)],
            [LLMStreamEventDTO(type="token", text="hi"), LLMStreamEventDTO(type="done")],
        ]
    )
    events = [e async for e in _resilient(inner).stream(MESSAGES)]
    assert [e.type for e in events] == ["token", "done"]
    assert inner.stream_attempts == 2


async def test_stream_does_not_retry_after_first_event() -> None:
    inner = ScriptedInner(
        stream_outcomes=[
            [LLMStreamEventDTO(type="token", text="hi"), LLMUnavailableError("503", retryable=True)]
        ]
    )
    with pytest.raises(LLMUnavailableError):
        _ = [e async for e in _resilient(inner).stream(MESSAGES)]
    assert inner.stream_attempts == 1
