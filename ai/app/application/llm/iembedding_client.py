from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

ERROR_RATE_LIMITED = "rate_limited"
ERROR_UNAUTHORIZED = "unauthorized"
ERROR_BAD_REQUEST = "bad_request"
ERROR_UNAVAILABLE = "provider_unavailable"
ERROR_MALFORMED = "malformed_response"

RETRYABLE = frozenset({ERROR_RATE_LIMITED, ERROR_UNAVAILABLE})


class EmbeddingError(Exception):
    def __init__(self, message: str, *, code: str = ERROR_UNAVAILABLE) -> None:
        super().__init__(message)
        self.code = code

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE


def classify_http_error(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return ERROR_RATE_LIMITED
    if status in (401, 403):
        return ERROR_UNAUTHORIZED
    if status == 400:
        return ERROR_BAD_REQUEST
    return ERROR_UNAVAILABLE


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    dimensions: int


class IEmbeddingClient(ABC):
    @property
    @abstractmethod
    def model(self) -> str: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch: ...

    @abstractmethod
    async def embed_query(self, text: str) -> EmbeddingBatch: ...


def validated_batch(
    vectors: tuple[tuple[float, ...], ...],
    texts: Sequence[str],
    model: str,
    expected: int | None,
) -> EmbeddingBatch:
    if len(vectors) != len(texts):
        raise EmbeddingError(f"expected {len(texts)} vectors, received {len(vectors)}")
    if not vectors:
        return EmbeddingBatch(vectors=(), model=model, dimensions=expected or 0)

    width = len(vectors[0])
    if any(len(vector) != width for vector in vectors):
        raise EmbeddingError("provider returned vectors of differing widths")
    if expected and width != expected:
        raise EmbeddingError(f"expected {expected} dimensions, received {width}")
    return EmbeddingBatch(vectors=vectors, model=model, dimensions=width)
