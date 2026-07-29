from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

# Failure codes. A caller has to be able to tell "wait and try again" from "an operator must
# look at this" — §12's fallback rules and §11's attempt cap mean opposite things for the two —
# and an exception whose only distinguishing feature is the word "HTTPStatusError" cannot.
ERROR_RATE_LIMITED = "rate_limited"
ERROR_UNAUTHORIZED = "unauthorized"
ERROR_BAD_REQUEST = "bad_request"
ERROR_UNAVAILABLE = "provider_unavailable"
ERROR_MALFORMED = "malformed_response"

# The transient half. Everything else is a configuration or contract problem that retrying only
# makes more expensive.
RETRYABLE = frozenset({ERROR_RATE_LIMITED, ERROR_UNAVAILABLE})


class EmbeddingError(Exception):
    """The provider could not produce usable vectors.

    Never carries a provider message verbatim — §14.4 keeps keys and internals out of anything an
    operator reads, and §12 turns this into a degradation rather than a 500.
    """

    def __init__(self, message: str, *, code: str = ERROR_UNAVAILABLE) -> None:
        super().__init__(message)
        self.code = code

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE


def classify_http_error(exc: Exception) -> str:
    """Map a transport failure onto a code, reading only the status.

    Found the hard way: a rate limit and a revoked key both surfaced as
    "embedding request failed (HTTPStatusError)", which tells the index worker nothing about
    whether to back off or stop. 429 is the one that must not burn an attempt.
    """
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
    """Vectors for one batch, in the order the texts were supplied.

    `model` and `dimensions` come back with the vectors rather than being assumed, because §10.2
    stores both beside every document: a backfill half-written by one model and half by another
    is otherwise undetectable, and §12 lists "malformed dimensions" as a fallback trigger that
    something has to actually detect.
    """

    vectors: tuple[tuple[float, ...], ...]
    model: str
    dimensions: int


class IEmbeddingClient(ABC):
    """One embedding provider, behind the shape §18 requires of all of them.

    Two calls, not one, because the same text embeds differently depending on its role. Most
    multilingual retrieval models are trained with an asymmetric instruction format — a query
    prefix and a document prefix — and §18 requires that format to be "applied identically at
    index time and query time". Splitting the methods makes forgetting it a type error rather
    than a silent recall loss that only the corpus would ever catch.

    No provider's wire format may leak past this interface (§18). The adapter owns batching,
    truncation, instruction prefixes, and normalization; callers see floats.
    """

    @property
    @abstractmethod
    def model(self) -> str:
        """The exact model identifier, as stored beside every document."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector width. Fixed per model, and baked into the schema once chosen (§18.1 step 6)."""

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed product documents as a batch.

        §18 requires a batch endpoint so a backfill is not one HTTP call per product. The
        adapter may split an oversized batch internally; the caller supplies whatever the index
        worker claimed and gets vectors back in the same order.
        """

    @abstractmethod
    async def embed_query(self, text: str) -> EmbeddingBatch:
        """Embed one shopper query, with the query-side instruction format."""


def validated_batch(
    vectors: tuple[tuple[float, ...], ...],
    texts: Sequence[str],
    model: str,
    expected: int | None,
) -> EmbeddingBatch:
    """Check count and width before anything is stored.

    §12 lists "returns malformed dimensions" as a fallback trigger, which only works if something
    looks. A short batch is worse than a failed one: the vectors would be written against the
    wrong products, and every later query would be quietly wrong with nothing to point at.
    """
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
