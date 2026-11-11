from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.application.llm.illm_client import ILLMClient
from app.application.llm.llm_dtos import (
    LLMMessageDTO,
    LLMReplyDTO,
    LLMStreamEventDTO,
    LLMToolCallDTO,
    LLMUsageDTO,
)
from app.core.config import Settings
from app.core.exceptions import LLMUnavailableError
from app.core.logging import log_llm_usage

_CHAT_PATH = "/api/v1/chat/completions"
_DAILY_ALLOWANCE_MARKER = "per-day"


class OpenRouterClient(ILLMClient):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._model = settings.LLM_MODEL
        self._fallback_models = settings.llm_fallback_models
        self._max_tokens = settings.MAX_TOKENS_PER_REPLY
        self._client = client or httpx.AsyncClient(
            base_url=settings.LLM_HOST or "https://openrouter.ai",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "HTTP-Referer": settings.STOREFRONT_URL,
                "X-OpenRouter-Title": settings.STORE_NAME,
            },
            timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS),
        )

    def _payload(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": [_encode_message(m) for m in messages],
            "stream": stream,
            "max_tokens": self._max_tokens,
            "reasoning": {"enabled": False},
        }
        if self._fallback_models:
            payload["models"] = [self._model, *self._fallback_models]
        else:
            payload["model"] = self._model
        if tools:
            payload["tools"] = tools
        return payload

    async def chat(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> LLMReplyDTO:
        started = time.perf_counter()
        try:
            response = await self._client.post(
                _CHAT_PATH, json=self._payload(messages, tools, stream=False)
            )
            if response.is_error:
                raise _status_error(response.status_code, response.text)
            data = response.json()
        except httpx.RequestError as exc:
            raise _transport_error(exc) from exc
        except ValueError as exc:
            raise _malformed() from exc

        _raise_on_error(data)
        choice = (data.get("choices") or [{}])[0]
        _raise_on_error(choice)
        message = choice.get("message") or {}
        usage = _usage(data.get("usage"), started)
        log_llm_usage(
            data.get("model") or self._model,
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.duration_ms,
        )
        return LLMReplyDTO(
            content=message.get("content") or "",
            tool_calls=[
                _tool_call(
                    item.get("id"),
                    (item.get("function") or {}).get("name"),
                    (item.get("function") or {}).get("arguments"),
                )
                for item in message.get("tool_calls") or []
            ],
            usage=usage,
        )

    async def stream(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMStreamEventDTO]:
        started = time.perf_counter()
        pending: dict[int, dict[str, Any]] = {}
        usage_raw: dict[str, Any] | None = None
        served_by = self._model
        try:
            async with self._client.stream(
                "POST", _CHAT_PATH, json=self._payload(messages, tools, stream=True)
            ) as response:
                if response.is_error:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise _status_error(response.status_code, body)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    _raise_on_error(chunk)
                    if chunk.get("usage"):
                        usage_raw = chunk["usage"]
                    served_by = chunk.get("model") or served_by

                    for choice in chunk.get("choices") or []:
                        _raise_on_error(choice)
                        delta = choice.get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield LLMStreamEventDTO(type="token", text=text)
                        for part in delta.get("tool_calls") or []:
                            _accumulate(pending, part)
        except httpx.RequestError as exc:
            raise _transport_error(exc) from exc
        except ValueError as exc:
            raise _malformed() from exc

        for index in sorted(pending):
            call = pending[index]
            yield LLMStreamEventDTO(
                type="tool_call",
                tool_call=_tool_call(call["id"], call["name"], call["arguments"]),
            )

        usage = _usage(usage_raw, started)
        log_llm_usage(served_by, usage.prompt_tokens, usage.completion_tokens, usage.duration_ms)
        yield LLMStreamEventDTO(type="done", usage=usage)


def _encode_message(message: LLMMessageDTO) -> dict[str, Any]:
    encoded: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        encoded["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.role == "tool":
        encoded["tool_call_id"] = message.tool_call_id
        if message.tool_name is not None:
            encoded["name"] = message.tool_name
    return encoded


def _accumulate(pending: dict[int, dict[str, Any]], part: dict[str, Any]) -> None:
    call = pending.setdefault(part.get("index", 0), {"id": None, "name": "", "arguments": ""})
    if part.get("id"):
        call["id"] = part["id"]
    fn = part.get("function") or {}
    if fn.get("name"):
        call["name"] += fn["name"]
    if fn.get("arguments"):
        call["arguments"] += fn["arguments"]


def _tool_call(call_id: str | None, name: str | None, arguments: Any) -> LLMToolCallDTO:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return LLMToolCallDTO(
        name=name or "", arguments=arguments, id=call_id or f"call_{uuid.uuid4().hex[:24]}"
    )


def _usage(raw: dict[str, Any] | None, started: float) -> LLMUsageDTO:
    raw = raw or {}
    return LLMUsageDTO(
        prompt_tokens=raw.get("prompt_tokens", 0) or 0,
        completion_tokens=raw.get("completion_tokens", 0) or 0,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


def _raise_on_error(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if not error:
        return
    if not isinstance(error, dict):
        raise _status_error(None, str(error))
    code = error.get("code")
    raise _status_error(code if isinstance(code, int) else None, json.dumps(error))


def _status_error(status: int | None, body: str) -> LLMUnavailableError:
    if status == 401:
        return LLMUnavailableError(
            "OpenRouter rejected the API key (check LLM_API_KEY)", retryable=False
        )
    if status == 402:
        return LLMUnavailableError(
            "OpenRouter credits exhausted (HTTP 402)", retryable=False, quota_exhausted=True
        )
    if status == 429 and _DAILY_ALLOWANCE_MARKER in body.lower():
        return LLMUnavailableError(
            "OpenRouter daily free-model allowance reached (HTTP 429)",
            retryable=False,
            quota_exhausted=True,
        )
    retryable = status is None or status in (408, 429) or status >= 500
    label = f"HTTP {status}" if status is not None else "error in response"
    return LLMUnavailableError(f"OpenRouter error ({label}): {body[:300]}", retryable=retryable)


def _transport_error(exc: httpx.RequestError) -> LLMUnavailableError:
    return LLMUnavailableError(f"OpenRouter unreachable ({type(exc).__name__})", retryable=True)


def _malformed() -> LLMUnavailableError:
    return LLMUnavailableError("OpenRouter sent a malformed response", retryable=True)
