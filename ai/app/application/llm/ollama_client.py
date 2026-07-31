from __future__ import annotations

import json
import time
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


class OllamaClient(ILLMClient):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._model = settings.OLLAMA_MODEL
        self._num_predict = settings.MAX_TOKENS_PER_REPLY
        self._client = client or httpx.AsyncClient(
            base_url=settings.OLLAMA_HOST,
            headers={"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"},
            timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS),
        )

    def _payload(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [_encode_message(m) for m in messages],
            "stream": stream,
            "think": False,
            "options": {"num_predict": self._num_predict},
        }
        if tools:
            payload["tools"] = tools
        return payload

    async def chat(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> LLMReplyDTO:
        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/api/chat", json=self._payload(messages, tools, stream=False)
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise _status_error(exc) from exc
        except httpx.RequestError as exc:
            raise _transport_error(exc) from exc

        message = data.get("message", {})
        usage = _usage(data, started)
        log_llm_usage(self._model, usage.prompt_tokens, usage.completion_tokens, usage.duration_ms)
        return LLMReplyDTO(
            content=message.get("content", "") or "",
            tool_calls=_tool_calls(message.get("tool_calls")),
            usage=usage,
        )

    async def stream(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMStreamEventDTO]:
        started = time.perf_counter()
        try:
            async with self._client.stream(
                "POST", "/api/chat", json=self._payload(messages, tools, stream=True)
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    message = chunk.get("message") or {}

                    text = message.get("content")
                    if text:
                        yield LLMStreamEventDTO(type="token", text=text)

                    for call in _tool_calls(message.get("tool_calls")):
                        yield LLMStreamEventDTO(type="tool_call", tool_call=call)

                    if chunk.get("done"):
                        usage = _usage(chunk, started)
                        log_llm_usage(
                            self._model,
                            usage.prompt_tokens,
                            usage.completion_tokens,
                            usage.duration_ms,
                        )
                        yield LLMStreamEventDTO(type="done", usage=usage)
        except httpx.HTTPStatusError as exc:
            raise _status_error(exc) from exc
        except httpx.RequestError as exc:
            raise _transport_error(exc) from exc


def _encode_message(message: LLMMessageDTO) -> dict[str, Any]:
    encoded: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        encoded["tool_calls"] = [
            {"function": {"name": c.name, "arguments": c.arguments}} for c in message.tool_calls
        ]
    if message.tool_name is not None:
        encoded["tool_name"] = message.tool_name
    return encoded


def _tool_calls(raw: list[dict[str, Any]] | None) -> list[LLMToolCallDTO]:
    calls: list[LLMToolCallDTO] = []
    for item in raw or []:
        fn = item.get("function", {})
        arguments = fn.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        calls.append(LLMToolCallDTO(name=fn.get("name", ""), arguments=arguments or {}))
    return calls


def _usage(data: dict[str, Any], started: float) -> LLMUsageDTO:
    return LLMUsageDTO(
        prompt_tokens=data.get("prompt_eval_count", 0) or 0,
        completion_tokens=data.get("eval_count", 0) or 0,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


def _status_error(exc: httpx.HTTPStatusError) -> LLMUnavailableError:
    status = exc.response.status_code
    if status in (401, 403):
        return LLMUnavailableError(
            "Ollama Cloud rejected the API key (check OLLAMA_API_KEY)", retryable=False
        )
    retryable = status == 429 or status >= 500
    return LLMUnavailableError(f"Ollama Cloud error (HTTP {status})", retryable=retryable)


def _transport_error(exc: httpx.RequestError) -> LLMUnavailableError:
    return LLMUnavailableError(f"Ollama Cloud unreachable ({type(exc).__name__})", retryable=True)
