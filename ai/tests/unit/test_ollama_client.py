from __future__ import annotations

import json

import httpx
import pytest

from app.application.llm.llm_dtos import LLMMessageDTO, LLMToolCallDTO
from app.application.llm.ollama_client import OllamaClient
from app.core.config import Settings
from app.core.exceptions import LLMUnavailableError

MESSAGES = [LLMMessageDTO(role="user", content="hi")]


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://u:p@h/db",
        INTERNAL_API_KEY="x" * 16,
        MCP_BEARER_TOKEN="y" * 16,
        OLLAMA_API_KEY="test-key",
        OLLAMA_MODEL="test-model",
    )


def _client(handler) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="https://ollama.test")
    return OllamaClient(_settings(), client=http)


async def test_chat_non_stream_parses_content_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Hello there"},
                "done": True,
                "prompt_eval_count": 11,
                "eval_count": 7,
            },
        )

    reply = await _client(handler).chat(MESSAGES)
    assert reply.content == "Hello there"
    assert reply.usage.prompt_tokens == 11
    assert reply.usage.completion_tokens == 7


async def test_chat_parses_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "search_products", "arguments": {"query": "tent"}}}
                    ],
                },
                "done": True,
            },
        )

    reply = await _client(handler).chat(MESSAGES)
    assert reply.tool_calls == [LLMToolCallDTO(name="search_products", arguments={"query": "tent"})]


async def test_stream_yields_tokens_tool_calls_and_done() -> None:
    lines = [
        {"message": {"content": "Let me "}, "done": False},
        {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "store_stats", "arguments": {}}}],
            },
            "done": False,
        },
        {"message": {"content": "here"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 5, "eval_count": 9},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = "\n".join(json.dumps(line) for line in lines)
        return httpx.Response(200, text=body)

    events = [e async for e in _client(handler).stream(MESSAGES)]
    types = [e.type for e in events]
    assert types == ["token", "tool_call", "token", "done"]
    assert events[1].tool_call.name == "store_stats"
    assert events[-1].usage.completion_tokens == 9


async def test_bad_api_key_is_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is False


async def test_server_error_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is True


async def test_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is True
