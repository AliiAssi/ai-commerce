from __future__ import annotations

import logging
from collections.abc import Sequence

from app.application.llm.iembedding_client import EmbeddingBatch, EmbeddingError, IEmbeddingClient
from app.core.vector_schema import FALLBACK_SLOT, PRIMARY_SLOT, EmbeddingSlot

logger = logging.getLogger(__name__)


class EmbeddingProviders:
    def __init__(
        self, primary: IEmbeddingClient | None, fallback: IEmbeddingClient | None = None
    ) -> None:
        self._clients: dict[EmbeddingSlot, IEmbeddingClient] = {}
        if primary is not None:
            self._clients[PRIMARY_SLOT] = primary
        if fallback is not None:
            self._clients[FALLBACK_SLOT] = fallback

    @property
    def configured(self) -> tuple[EmbeddingSlot, ...]:
        return tuple(slot for slot in (PRIMARY_SLOT, FALLBACK_SLOT) if slot in self._clients)

    @property
    def any_configured(self) -> bool:
        return bool(self._clients)

    def client(self, slot: EmbeddingSlot) -> IEmbeddingClient | None:
        return self._clients.get(slot)

    def model(self, slot: EmbeddingSlot) -> str | None:
        client = self._clients.get(slot)
        return client.model if client else None

    def dimensions(self, slot: EmbeddingSlot) -> int | None:
        client = self._clients.get(slot)
        return client.dimensions if client else None

    async def embed_documents(
        self, slot: EmbeddingSlot, texts: Sequence[str]
    ) -> EmbeddingBatch | None:
        client = self._clients.get(slot)
        if client is None:
            return None
        return await client.embed_documents(texts)

    async def embed_query(self, text: str) -> tuple[EmbeddingBatch, EmbeddingSlot]:
        last: EmbeddingError | None = None
        for slot in self.configured:
            try:
                return await self._clients[slot].embed_query(text), slot
            except EmbeddingError as exc:
                last = exc
                logger.warning("embedding provider %s failed to embed a query (%s)", slot, exc.code)
        if last is not None:
            raise last
        raise EmbeddingError("no embedding provider is configured")
