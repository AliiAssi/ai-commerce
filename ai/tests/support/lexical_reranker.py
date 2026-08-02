from __future__ import annotations

from collections.abc import Sequence

from app.application.dtos.search_dto import SearchIntent
from app.application.rerank.ireranker import RerankCandidate, ScoringReranker
from app.application.search.normalizer import detect_language, tokenize

_STOPWORDS = frozenset(
    [
        *("a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from"),
        *("in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "with"),
        *("available", "something", "some", "any", "my", "your", "our"),
        *("need", "want", "looking", "good", "best", "under", "over"),
    ]
)


def _terms(text: str) -> list[str]:
    return [token.replace("'", "") for token in tokenize(text.casefold()) if token.strip("'")]


class LexicalReranker(ScoringReranker):
    @property
    def version(self) -> str:
        return "lexical-overlap-1"

    async def score(
        self, intent: SearchIntent, candidates: Sequence[RerankCandidate]
    ) -> Sequence[float]:
        query = intent.semantic_text or intent.normalized_query
        terms = [token for token in _terms(query) if token not in _STOPWORDS]
        if not terms or detect_language(query) != "en":
            return self._abstain(candidates)

        scores: list[float] = []
        for candidate in candidates:
            document = set(_terms(candidate.document_text))
            hits = sum(1 for term in terms if term in document)
            partial = sum(
                1
                for term in terms
                if term not in document and any(term in word for word in document)
            )
            scores.append(min(1.0, (hits + 0.4 * partial) / len(terms)))

        # A scorer that found nothing anywhere has no opinion, and an opinionless scorer must
        # not be what empties a result set. Real cross-encoders separate these cases fine —
        # "natural sweetener" against honey scores well for them and zero for word overlap —
        # so scoring them all alike keeps this stand-in from inventing a relevance verdict.
        if not any(scores):
            return self._abstain(candidates)
        return scores

    @staticmethod
    def _abstain(candidates: Sequence[RerankCandidate]) -> list[float]:
        return [1.0] * len(candidates)
