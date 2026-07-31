from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.application.dtos.search_dto import SearchIntent
from app.application.rerank.ireranker import (
    ERROR_MALFORMED,
    RerankCandidate,
    RerankError,
    ScoringReranker,
    classify_http_error,
)
from app.core.config import Settings

_ROUTER_BASE = "https://router.huggingface.co"


class HuggingFaceReranker(ScoringReranker):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._model = settings.RERANKER_MODEL
        self._client = client or httpx.AsyncClient(
            base_url=settings.RERANKER_HOST or _ROUTER_BASE,
            headers={
                "Authorization": f"Bearer {settings.RERANKER_API_KEY}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(settings.RERANKER_TIMEOUT_SECONDS),
        )

    @property
    def version(self) -> str:
        return f"hf:{self._model}"

    async def score(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate]
    ) -> Sequence[float]:
        query = intent.semantic_text or intent.normalized_query
        request = {
            "inputs": [
                {"text": query, "text_pair": candidate.document_text} for candidate in candidates
            ]
        }
        try:
            response = await self._client.post(f"/hf-inference/models/{self._model}", json=request)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise RerankError(
                f"rerank request failed ({exc.__class__.__name__})",
                code=classify_http_error(exc, exc.response.text),
            ) from exc
        except httpx.HTTPError as exc:
            raise RerankError(
                f"rerank request failed ({exc.__class__.__name__})",
                code=classify_http_error(exc),
            ) from exc

        return _scores_from_payload(payload, len(candidates))


def _scores_from_payload(payload: object, expected: int) -> list[float]:
    if not isinstance(payload, list) or not payload:
        raise RerankError("rerank response was not a list", code=ERROR_MALFORMED)

    def label_score(entry: object) -> float:
        if not isinstance(entry, dict) or "score" not in entry:
            raise RerankError("rerank response held no score", code=ERROR_MALFORMED)
        return float(entry["score"])

    first = payload[0]
    if len(payload) == 1 and isinstance(first, list) and len(first) == expected:
        return [label_score(entry) for entry in first]
    if len(payload) == expected:
        scores = []
        for group in payload:
            if isinstance(group, list) and group:
                scores.append(label_score(group[0]))
            else:
                scores.append(label_score(group))
        return scores
    raise RerankError(
        f"expected {expected} scores, received a payload of {len(payload)}", code=ERROR_MALFORMED
    )
