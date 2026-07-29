from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
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

    def peek(self, interface: type[T]) -> T | None:
        return self._instances.get(interface) or self._singletons.get(interface)

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

    def _resolve_dependency(self, annotation: type, scope: Scope | None) -> Any:
        if scope is not None:
            cached = scope.get_cached(annotation)
            if cached is not None:
                return cached
        if annotation is AsyncSession:
            raise LookupError(
                "AsyncSession is only available inside a request scope "
                "(singletons must not depend on the database session)"
            )
        return self.resolve(annotation, scope)

    # A scope whose lifetime is one unit of work rather than one request.
    #
    # get_scope() below holds a transaction open for the whole request, which is right for
    # ordinary handlers but wrong for anything that calls an external provider mid-flight: the
    # call would run with a connection checked out and a transaction sitting idle, and a slow
    # provider would pin a connection from a small pool. Callers that talk to the network split
    # their work instead — read, close, call, reopen, write:
    #
    #     async with container.open_scope() as scope:
    #         candidates = await scope.resolve(ISearchRepository).candidates(...)
    #     vector = await embedding_client.embed(text)      # no transaction held
    #     async with container.open_scope() as scope:
    #         await scope.resolve(ISearchRepository).store(...)
    #
    # Each block is its own session, transaction, and Scope cache, so no instance is shared
    # across the provider call. Also used by background workers and CLI jobs, which have no
    # request to hang a scope off at all.
    @asynccontextmanager
    async def open_scope(self) -> AsyncIterator[Scope]:
        if self.session_factory is None:
            raise RuntimeError("Container is not configured (core/registry.py not applied)")
        async with self.session_factory() as session, session.begin():
            yield Scope(self, session)


container = Container()


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


# The request-path counterpart to Container.open_scope(). A handler depending on this gets no
# session and no transaction — only the ability to open short ones around its own database
# work. Depending on Injected(...) instead would defeat the point, because get_scope would
# already have opened a request-long transaction before the handler body ran.
class ScopeFactory:
    __slots__ = ("_container",)

    def __init__(self, container: Container) -> None:
        self._container = container

    def open(self) -> AbstractAsyncContextManager[Scope]:
        return self._container.open_scope()


def InjectedScopes() -> Any:
    async def provider() -> ScopeFactory:
        return ScopeFactory(container)

    provider.__name__ = "inject_scope_factory"
    return Depends(provider)
