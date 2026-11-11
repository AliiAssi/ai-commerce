from __future__ import annotations

import json

import httpx
import pytest

from app.application.llm.llm_dtos import LLMMessageDTO, LLMToolCallDTO
from app.application.llm.openrouter_client import OpenRouterClient
from app.core.config import Settings
from app.core.exceptions import LLMUnavailableError

MESSAGES = [LLMMessageDTO(role="user", content="hi")]


def _settings(**overrides) -> Settings:
    base = dict(
        DATABASE_URL="postgresql://u:p@h/db",
        INTERNAL_API_KEY="x" * 16,
        MCP_BEARER_TOKEN="y" * 16,
        LLM_API_KEY="test-key",
        LLM_MODEL="test-model",
        LLM_FALLBACK_MODELS="",
    )
    base.update(overrides)
    return Settings(**base)


def _client(handler, **overrides) -> OpenRouterClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="https://openrouter.test")
    return OpenRouterClient(_settings(**overrides), client=http)


def _sse(*chunks: dict | str) -> str:
    lines = [": OPENROUTER PROCESSING", ""]
    for chunk in chunks:
        lines += [f"data: {chunk if isinstance(chunk, str) else json.dumps(chunk)}", ""]
    return "\n".join(lines)


def test_the_default_client_identifies_the_store_to_openrouter() -> None:
    client = OpenRouterClient(_settings())
    assert str(client._client.base_url) == "https://openrouter.ai"
    assert client._client.headers["authorization"] == "Bearer test-key"
    assert client._client.headers["x-openrouter-title"] == "BEIT"


async def test_chat_non_stream_parses_content_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/v1/chat/completions"
        assert body["model"] == "test-model"
        assert "models" not in body
        assert body["stream"] is False
        assert body["reasoning"] == {"enabled": False}
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Hello there"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    reply = await _client(handler).chat(MESSAGES)
    assert reply.content == "Hello there"
    assert reply.usage.prompt_tokens == 11
    assert reply.usage.completion_tokens == 7


async def test_fallback_models_are_offered_after_the_primary_in_order() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"model": "backup-a", "choices": [{"message": {"content": "hi"}}]}
        )

    client = _client(handler, LLM_FALLBACK_MODELS="backup-a, backup-b")
    reply = await client.chat(MESSAGES)

    assert reply.content == "hi"
    assert seen["models"] == ["test-model", "backup-a", "backup-b"]
    assert "model" not in seen


async def test_usage_is_logged_against_the_model_that_answered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = _sse(
        {"model": "backup-a", "choices": [{"delta": {"content": "hi"}}]},
        {"model": "backup-a", "choices": [], "usage": {"prompt_tokens": 1}},
        "[DONE]",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    with caplog.at_level("INFO"):
        _ = [e async for e in _client(handler, LLM_FALLBACK_MODELS="backup-a").stream(MESSAGES)]
    assert any("model=backup-a" in r.getMessage() for r in caplog.records)


async def test_chat_parses_tool_calls_with_json_string_arguments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_products",
                                        "arguments": '{"query": "tent"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    reply = await _client(handler).chat(MESSAGES)
    assert reply.content == ""
    assert reply.tool_calls == [
        LLMToolCallDTO(name="search_products", arguments={"query": "tent"}, id="call_1")
    ]


async def test_a_tool_round_trip_is_encoded_in_the_openai_shape() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}]})

    call = LLMToolCallDTO(name="get_product", arguments={"product_id": 3}, id="call_9")
    await _client(handler).chat(
        [
            LLMMessageDTO(role="user", content="tell me about 3"),
            LLMMessageDTO(role="assistant", content="", tool_calls=[call]),
            LLMMessageDTO(
                role="tool", content='{"id": 3}', tool_name="get_product", tool_call_id="call_9"
            ),
        ],
        tools=[{"type": "function", "function": {"name": "get_product"}}],
    )

    assert seen["tools"] == [{"type": "function", "function": {"name": "get_product"}}]
    assert seen["messages"][1]["tool_calls"] == [
        {
            "id": "call_9",
            "type": "function",
            "function": {"name": "get_product", "arguments": '{"product_id": 3}'},
        }
    ]
    assert seen["messages"][2] == {
        "role": "tool",
        "content": '{"id": 3}',
        "tool_call_id": "call_9",
        "name": "get_product",
    }


async def test_stream_yields_tokens_then_assembled_tool_calls_then_done() -> None:
    body = _sse(
        {"choices": [{"delta": {"role": "assistant", "content": "Let me "}}]},
        {"choices": [{"delta": {"content": "look"}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_a",
                                "function": {"name": "search_products", "arguments": '{"que'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'ry": "oil"}'}}]}}
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "call_b",
                                "function": {"name": "store_stats", "arguments": ""},
                            }
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 9}},
        "[DONE]",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=body)

    events = [e async for e in _client(handler).stream(MESSAGES)]
    assert [e.type for e in events] == ["token", "token", "tool_call", "tool_call", "done"]
    assert events[2].tool_call == LLMToolCallDTO(
        name="search_products", arguments={"query": "oil"}, id="call_a"
    )
    assert events[3].tool_call == LLMToolCallDTO(name="store_stats", arguments={}, id="call_b")
    assert events[-1].usage.prompt_tokens == 5
    assert events[-1].usage.completion_tokens == 9


async def test_a_tool_call_without_an_id_is_given_one() -> None:
    body = _sse(
        {"choices": [{"delta": {"tool_calls": [{"function": {"name": "store_stats"}}]}}]},
        "[DONE]",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    events = [e async for e in _client(handler).stream(MESSAGES)]
    assert events[0].tool_call.id.startswith("call_")


async def test_an_error_sent_mid_stream_is_raised() -> None:
    body = _sse(
        {"choices": [{"delta": {"content": "Sure"}}]},
        {
            "error": {"code": 502, "message": "Provider disconnected"},
            "choices": [{"delta": {}, "finish_reason": "error"}],
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    with pytest.raises(LLMUnavailableError) as exc:
        _ = [e async for e in _client(handler).stream(MESSAGES)]
    assert exc.value.retryable is True


async def test_a_failed_stream_request_is_classified_from_its_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day"}},
        )

    with pytest.raises(LLMUnavailableError) as exc:
        _ = [e async for e in _client(handler).stream(MESSAGES)]
    assert exc.value.quota_exhausted is True
    assert exc.value.retryable is False


async def test_bad_api_key_is_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": 401, "message": "No auth"}})

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is False
    assert exc.value.quota_exhausted is False


async def test_spent_credits_are_fatal_quota_exhaustion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"code": 402, "message": "Insufficient credits"}})

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is False
    assert exc.value.quota_exhausted is True


async def test_a_busy_upstream_is_retryable_and_not_quota() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "message": "Provider returned error",
                    "metadata": {"raw": "test-model is temporarily rate-limited upstream."},
                }
            },
        )

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is True
    assert exc.value.quota_exhausted is False


async def test_server_error_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"code": 503, "message": "No provider"}})

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is True


async def test_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is True


async def test_a_body_that_is_not_json_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>bad gateway</html>")

    with pytest.raises(LLMUnavailableError) as exc:
        await _client(handler).chat(MESSAGES)
    assert exc.value.retryable is True
