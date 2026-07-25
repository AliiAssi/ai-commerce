from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar, get_type_hints

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

T = TypeVar("T")


class _Binding:
    __slots__ = ("implementation", "singleton")

    def __init__(self, implementation: type, singleton: bool) -> None:
        self.implementation = implementation
        self.singleton = singleton


class Scope:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self._container = container
        self._cache: dict[type, Any] = {AsyncSession: session}

    def resolve(self, interface: type[T]) -> T:
        cached = self._cache.get(interface)
        if cached is not None:
            return cached
        return self._container.resolve(interface, scope=self)

    # Instances cached here live only as long as this request's scope does.
    def cache(self, interface: type, instance: Any) -> None:
        self._cache[interface] = instance

    def get_cached(self, interface: type) -> Any:
        return self._cache.get(interface)


class Container:
    def __init__(self) -> None:
        self._bindings: dict[type, _Binding] = {}
        self._instances: dict[type, Any] = {}
        self._singletons: dict[type, Any] = {}
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    def bind(self, interface: type, implementation: type, *, singleton: bool = False) -> None:
        self._bindings[interface] = _Binding(implementation, singleton)
        self._singletons.pop(interface, None)

    def bind_instance(self, interface: type, instance: Any) -> None:
        self._instances[interface] = instance

    # Used between tests so bindings from one test don't leak into the next.
    def reset(self) -> None:
        self._bindings.clear()
        self._instances.clear()
        self._singletons.clear()

    def resolve(self, interface: type[T], scope: Scope | None = None) -> T:
        if interface in self._instances:
            return self._instances[interface]
        if interface in self._singletons:
            return self._singletons[interface]

        binding = self._bindings.get(interface)
        if binding is None:
            raise LookupError(f"No binding registered for {interface!r}")

        if binding.singleton:
            instance = self._construct(binding.implementation, scope=None)
            self._singletons[interface] = instance
            return instance

        if scope is not None:
            cached = scope.get_cached(interface)
            if cached is None:
                cached = self._construct(binding.implementation, scope)
                scope.cache(interface, cached)
            return cached
        return self._construct(binding.implementation, scope)

    def _construct(self, implementation: type, scope: Scope | None) -> Any:
        init = implementation.__init__
        if init is object.__init__:
            return implementation()

        hints = get_type_hints(init)
        signature = inspect.signature(init)
        kwargs: dict[str, Any] = {}
        for name, param in list(signature.parameters.items())[1:]:
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            annotation = hints.get(name)
            if annotation is None:
                if param.default is not param.empty:
                    continue
                raise TypeError(
                    f"Cannot construct {implementation.__name__}: "
                    f"parameter {name!r} has no type annotation"
                )
            try:
                kwargs[name] = self._resolve_dependency(annotation, scope)
            except LookupError:
                if param.default is not param.empty:
                    continue
                raise LookupError(
                    f"Cannot construct {implementation.__name__}: "
                    f"no binding for {annotation!r} (parameter {name!r})"
                ) from None
        return implementation(**kwargs)

    # AsyncSession must come from the request scope; singletons can't depend on it directly.
    def _resolve_dependency(self, annotation: type, scope: Scope | None) -> Any:
        if scope is not None:
            cached = scope.get_cached(annotation)
            if cached is not None:
                return cached
        if annotation is AsyncSession:
            raise LookupError(
                "AsyncSession is only available inside a scope "
                "(singletons must not depend on the database session)"
            )
        return self.resolve(annotation, scope)


container = Container()


# For work outside a FastAPI request: MCP calls bypass Depends entirely, and the chat SSE
# generator can't use the request scope either since FastAPI closes yield-dependencies before
# a StreamingResponse body runs. Each tool call opens its own scope, so nothing stays pinned
# across a slow LLM turn.
@asynccontextmanager
async def open_scope() -> AsyncIterator[Scope]:
    if container.session_factory is None:
        raise RuntimeError("Container is not configured (core/registry.py not applied)")
    async with container.session_factory() as session, session.begin():
        yield Scope(container, session)


async def get_scope(request: Request) -> AsyncIterator[Scope]:
    if container.session_factory is None:
        raise RuntimeError("Container is not configured (core/registry.py not applied)")
    async with container.session_factory() as session, session.begin():
        yield Scope(container, session)


def Injected[I](interface: type[I]) -> Any:
    async def provider(scope: Scope = Depends(get_scope)) -> I:
        return scope.resolve(interface)

    provider.__name__ = f"inject_{getattr(interface, '__name__', 'dependency')}"
    return Depends(provider)
