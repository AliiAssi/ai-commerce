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

_RERANK_PATH = "/api/v1/rerank"

_REFERER = "https://beit.store"
_TITLE = "BEIT"


class OpenRouterReranker(ScoringReranker):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._model = settings.RERANKER_MODEL
        self._client = client or httpx.AsyncClient(
            base_url=settings.RERANKER_HOST or "https://openrouter.ai",
            headers={
                "Authorization": f"Bearer {settings.RERANKER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": _REFERER,
                "X-OpenRouter-Title": _TITLE,
            },
            timeout=httpx.Timeout(settings.RERANKER_TIMEOUT_SECONDS),
        )

    @property
    def version(self) -> str:
        return f"openrouter:{self._model}"

    async def score(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate]
    ) -> Sequence[float]:
        request = {
            "model": self._model,
            "query": intent.semantic_text or intent.normalized_query,
            "documents": [candidate.document_text for candidate in candidates],
            "top_n": len(candidates),
        }
        try:
            response = await self._client.post(_RERANK_PATH, json=request)
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

        try:
            results = payload["results"]
            scores = [0.0] * len(candidates)
            for item in results:
                scores[int(item["index"])] = float(item["relevance_score"])
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise RerankError(
                "rerank response was not in the expected shape", code=ERROR_MALFORMED
            ) from exc

        if len(results) != len(candidates):
            raise RerankError(
                f"expected {len(candidates)} scores, received {len(results)}", code=ERROR_MALFORMED
            )
        return scores
