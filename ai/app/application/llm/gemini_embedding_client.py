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

_DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
_QUERY_TASK = "RETRIEVAL_QUERY"

_MAX_INDEXABLE_DIMENSIONS = 2000


class GeminiEmbeddingClient(IEmbeddingClient):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._model = settings.EMBEDDING_MODEL
        self._dimensions = settings.EMBEDDING_DIMENSIONS
        if self._dimensions and self._dimensions > _MAX_INDEXABLE_DIMENSIONS:
            raise EmbeddingError(
                f"EMBEDDING_DIMENSIONS={self._dimensions} cannot be given an HNSW index; "
                f"pgvector supports at most {_MAX_INDEXABLE_DIMENSIONS}"
            )
        self._client = client or httpx.AsyncClient(
            base_url=settings.EMBEDDING_HOST or "https://generativelanguage.googleapis.com",
            headers={"x-goog-api-key": settings.EMBEDDING_API_KEY},
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
        return await self._embed(texts, _DOCUMENT_TASK)

    async def embed_query(self, text: str) -> EmbeddingBatch:
        return await self._embed([text], _QUERY_TASK)

    async def _embed(self, texts: Sequence[str], task: str) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=(), model=self._model, dimensions=self._dimensions or 0)

        request: dict[str, object] = {
            "requests": [
                {
                    "model": f"models/{self._model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": task,
                    **({"outputDimensionality": self._dimensions} if self._dimensions else {}),
                }
                for text in texts
            ]
        }
        try:
            response = await self._client.post(
                f"/v1beta/models/{self._model}:batchEmbedContents", json=request
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                f"embedding request failed ({exc.__class__.__name__})",
                code=classify_http_error(exc),
            ) from exc

        try:
            vectors = tuple(tuple(float(v) for v in e["values"]) for e in payload["embeddings"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(
                "embedding response was not in the expected shape", code=ERROR_MALFORMED
            ) from exc

        return validated_batch(vectors, texts, self._model, self._dimensions)
