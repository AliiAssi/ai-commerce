from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.application.dtos.tool_dto import ToolContext, ToolSpec
from app.application.events.bus import EventBus
from app.application.events.definitions import ToolExecuted
from app.core.container import Scope, ScopeFactory, open_scope
from app.core.exceptions import AppError, ToolExecutionError

logger = logging.getLogger(__name__)

ToolFn = Callable[[BaseModel, Scope], Awaitable[dict[str, Any]]]


class _Registered:
    __slots__ = ("fn", "spec")

    def __init__(self, spec: ToolSpec, fn: ToolFn) -> None:
        self.spec = spec
        self.fn = fn


class ToolRegistry:
    def __init__(
        self, events: EventBus | None = None, scope_factory: ScopeFactory = open_scope
    ) -> None:
        self._tools: dict[str, _Registered] = {}
        self._events = events
        self._scope_factory = scope_factory

    def register(self, spec: ToolSpec, fn: ToolFn) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} is already registered")
        self._tools[spec.name] = _Registered(spec, fn)

    def specs(self) -> list[ToolSpec]:
        return [entry.spec for entry in self._tools.values()]

    def spec(self, name: str) -> ToolSpec:
        return self._tools[name].spec

    def ollama_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": entry.spec.name,
                    "description": entry.spec.description,
                    "parameters": entry.spec.params_model.model_json_schema(),
                },
            }
            for entry in self._tools.values()
        ]

    async def execute(
        self, name: str, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        entry = self._tools.get(name)
        if entry is None:
            raise ToolExecutionError(f"unknown tool {name!r}")

        arguments = dict(arguments)
        if entry.spec.customer_scoped and context.source == "chat":
            arguments["user_email"] = context.user_email

        try:
            params = entry.spec.params_model.model_validate(arguments)
        except ValidationError as exc:
            fields = ", ".join(str(e["loc"][-1]) for e in exc.errors())
            raise ToolExecutionError(f"invalid arguments for {name}: {fields}") from exc

        started = time.perf_counter()
        ok = False
        try:
            async with self._scope_factory() as scope:
                result = await entry.fn(params, scope)
            ok = True
            return result
        except AppError:
            raise
        except Exception as exc:
            logger.exception("tool %s failed", name)
            raise ToolExecutionError(f"tool {name} failed") from exc
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            if self._events is not None:
                self._events.publish(ToolExecuted(name, context.source, duration_ms, ok))
