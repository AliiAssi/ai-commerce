from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.application.llm.iembedding_client import (
    ERROR_MALFORMED,
    EmbeddingBatch,
    EmbeddingError,
    IEmbeddingClient,
    classify_http_error,
    validated_batch,
)
from app.core.config import Settings

_MAX_INDEXABLE_DIMENSIONS = 2000


class OpenAICompatibleEmbeddingClient(IEmbeddingClient):
    """Any host serving OpenAI's `/v1/embeddings` — OpenRouter, OpenAI itself, and most gateways.

    The second adapter §18.1 requires, and deliberately against a different wire format rather
    than a second model on the same one: one flat `input` array, one `dimensions` integer, and
    results that must be re-sorted by their `index` field. Proving `IEmbeddingClient` survives
    both shapes is the whole reason the interface exists.

    **It has no notion of a task type.** A query and a document embed identically here, so the
    asymmetric query/document instruction format §18 asks for simply is not available. That is a
    real quality difference from the Gemini adapter and not an implementation shortcut; it is
    recorded here so a bake-off result is read with it in mind.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._model = settings.EMBEDDING_MODEL
        self._dimensions = settings.EMBEDDING_DIMENSIONS
        if self._dimensions and self._dimensions > _MAX_INDEXABLE_DIMENSIONS:
            raise EmbeddingError(
                f"EMBEDDING_DIMENSIONS={self._dimensions} cannot be given an HNSW index; "
                f"pgvector supports at most {_MAX_INDEXABLE_DIMENSIONS}"
            )
        self._client = client or httpx.AsyncClient(
            base_url=settings.EMBEDDING_HOST or "https://openrouter.ai",
            headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
            timeout=httpx.Timeout(settings.EMBEDDING_TIMEOUT_SECONDS),
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        if not self._dimensions:
            raise EmbeddingError("EMBEDDING_DIMENSIONS is not set")
        return self._dimensions

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> EmbeddingBatch:
        return await self._embed([text])

    async def _embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=(), model=self._model, dimensions=self._dimensions or 0)

        request: dict[str, object] = {"model": self._model, "input": list(texts)}
        if self._dimensions:
            request["dimensions"] = self._dimensions
        try:
            response = await self._client.post("/api/v1/embeddings", json=request)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                f"embedding request failed ({exc.__class__.__name__})",
                code=classify_http_error(exc),
            ) from exc

        try:
            # The spec allows results out of order, so `index` is authoritative and position is
            # not. Trusting position would silently pair vectors with the wrong products.
            rows = sorted(payload["data"], key=lambda row: row["index"])
            vectors = tuple(tuple(float(v) for v in row["embedding"]) for row in rows)
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(
                "embedding response was not in the expected shape", code=ERROR_MALFORMED
            ) from exc

        return validated_batch(vectors, texts, self._model, self._dimensions)
