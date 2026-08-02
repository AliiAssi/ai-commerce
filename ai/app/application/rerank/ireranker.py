from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.application.dtos.search_dto import SearchIntent

RERANK_APPLIED = "applied"
RERANK_SKIPPED = "skipped"
RERANK_UNAVAILABLE = "unavailable"

ERROR_RATE_LIMITED = "rate_limited"
ERROR_QUOTA_EXHAUSTED = "quota_exhausted"
ERROR_UNAUTHORIZED = "unauthorized"
ERROR_BAD_REQUEST = "bad_request"
ERROR_UNAVAILABLE = "provider_unavailable"
ERROR_MALFORMED = "malformed_response"

RETRYABLE = frozenset({ERROR_RATE_LIMITED, ERROR_UNAVAILABLE})


class RerankError(Exception):
    def __init__(self, message: str, *, code: str = ERROR_UNAVAILABLE) -> None:
        super().__init__(message)
        self.code = code

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE


def classify_http_error(exc: Exception, body: str = "") -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    haystack = body.lower()
    if status == 402:
        return ERROR_QUOTA_EXHAUSTED
    if status == 429:
        return ERROR_RATE_LIMITED
    if status in (401, 403):
        if "insufficient_balance" in haystack or "insufficient account balance" in haystack:
            return ERROR_QUOTA_EXHAUSTED
        return ERROR_UNAUTHORIZED
    if status == 400:
        return ERROR_BAD_REQUEST
    return ERROR_UNAVAILABLE


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    product_id: int
    document_text: str


class RerankResult:
    __slots__ = ("outcome", "product_ids", "scores", "version")

    def __init__(
        self,
        product_ids: Sequence[int],
        *,
        outcome: str,
        version: str = "",
        scores: Sequence[float | None] | None = None,
    ) -> None:
        self.product_ids = list(product_ids)
        self.scores = list(scores) if scores is not None else None
        self.outcome = outcome
        self.version = version

    @property
    def applied(self) -> bool:
        return self.outcome == RERANK_APPLIED


class IReranker(ABC):
    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult: ...


class PassthroughReranker(IReranker):
    @property
    def version(self) -> str:
        return "passthrough-1"

    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult:
        return RerankResult(
            [candidate.product_id for candidate in candidates],
            outcome=RERANK_SKIPPED,
            version=self.version,
        )


def order_by_scores(
    candidates: Sequence[RerankCandidate], scores: Sequence[float], *, window: int
) -> tuple[list[int], list[float | None]]:
    head = list(candidates[:window])
    tail = list(candidates[window:])
    if len(scores) != len(head):
        raise RerankError(
            f"expected {len(head)} scores, received {len(scores)}", code=ERROR_MALFORMED
        )
    ranked = sorted(range(len(head)), key=lambda i: -scores[i])
    ordered = [head[i].product_id for i in ranked] + [candidate.product_id for candidate in tail]
    ordered_scores: list[float | None] = [scores[i] for i in ranked] + [None] * len(tail)
    return ordered, ordered_scores


class ScoringReranker(IReranker):
    @abstractmethod
    async def score(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate]
    ) -> Sequence[float]: ...

    async def rerank(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate], *, window: int
    ) -> RerankResult:
        head = list(candidates[:window])
        if len(head) < 2:
            return RerankResult(
                [candidate.product_id for candidate in candidates],
                outcome=RERANK_SKIPPED,
                version=self.version,
            )

        scores = await self.score(intent, head)
        ordered, ordered_scores = order_by_scores(candidates, scores, window=window)
        return RerankResult(
            ordered, outcome=RERANK_APPLIED, version=self.version, scores=ordered_scores
        )
