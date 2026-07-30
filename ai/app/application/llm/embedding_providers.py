from __future__ import annotations

import logging
from collections.abc import Sequence

from app.application.llm.iembedding_client import EmbeddingBatch, EmbeddingError, IEmbeddingClient
from app.core.vector_schema import FALLBACK_SLOT, PRIMARY_SLOT, EmbeddingSlot

logger = logging.getLogger(__name__)


class EmbeddingProviders:
    """The configured embedding providers, each paired with the column it owns.

    Failover between embedding providers is a *column* choice, not a call-site retry, and this is
    the type that makes that unavoidable. Vectors from two models occupy different spaces, so a
    query embedded by the fallback and compared by cosine against primary-built vectors returns
    arbitrary neighbours — results that look like an answer and are not, which §12 rates worse
    than degrading. Every method here therefore hands back the slot alongside the vector, so a
    caller cannot hold one without the other.

    Bound as a single instance rather than two `IEmbeddingClient` bindings, because the container
    resolves by exact annotation and two bindings of one interface cannot both exist.
    """

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
        """The slots that have a client, primary first — which is also failover order."""
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
        """Embed a batch for one named slot. `None` when that slot has no provider configured.

        Never fails over. A document written into the primary column by the fallback's model
        would be undetectable at query time and would poison the column for every later search —
        the failure §10.2 stores `embedding_model` per row to make visible.
        """
        client = self._clients.get(slot)
        if client is None:
            return None
        return await client.embed_documents(texts)

    async def embed_query(self, text: str) -> tuple[EmbeddingBatch, EmbeddingSlot]:
        """One query vector, from the first provider that answers, with the slot it belongs to.

        This is where failover happens, and the only place it can: the returned slot tells
        retrieval which column to compare against, so the query and the documents always came
        from the same model.
        """
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
