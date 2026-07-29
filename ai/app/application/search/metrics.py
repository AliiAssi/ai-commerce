from __future__ import annotations

from collections.abc import Sequence
from math import log2

# Ranking metrics, as pure functions over a list of product ids.
#
# They live here rather than inside the scorer because §15's gates are stated in these terms and
# phase 7 has to compare a reranked order against the pre-rerank one using the same arithmetic.
# Two implementations of nDCG would make that comparison meaningless.


def reciprocal_rank(ranked_ids: Sequence[int], target_id: int) -> float:
    """1/rank of the target, or 0.0 when it is absent.

    §15's MRR gate covers the "MUST rank first" cases, so in practice this is 1.0 or a number
    that says exactly how badly the case missed — which is more useful than a boolean when a
    model change moves a result from rank 1 to rank 2.
    """
    for position, product_id in enumerate(ranked_ids, start=1):
        if product_id == target_id:
            return 1.0 / position
    return 0.0


def recall_at_k(ranked_ids: Sequence[int], required_ids: Sequence[int], k: int) -> float:
    """Share of the required products that appear in the first k results.

    Undefined with nothing required, and 1.0 is the only honest answer there: a case with no
    required products cannot lower recall, and returning 0.0 would drag the aggregate down for
    cases that were never about recall.
    """
    if not required_ids:
        return 1.0
    window = set(ranked_ids[:k])
    found = sum(1 for product_id in required_ids if product_id in window)
    return found / len(required_ids)


def dcg_at_k(ranked_ids: Sequence[int], relevant_ids: Sequence[int], k: int) -> float:
    """Binary-gain DCG. Position 1 counts fully; later positions are discounted by log2(1+rank)."""
    relevant = set(relevant_ids)
    return sum(
        1.0 / log2(position + 1)
        for position, product_id in enumerate(ranked_ids[:k], start=1)
        if product_id in relevant
    )


def ndcg_at_k(ranked_ids: Sequence[int], relevant_ids: Sequence[int], k: int) -> float:
    """DCG over the best achievable DCG for the same number of relevant products.

    Relevance is binary here because §15 judges membership, not degree: a case names the products
    that must come back, not how good each one is. Graded relevance would be a corpus change, not
    a metric change.
    """
    if not relevant_ids:
        return 1.0
    ideal = dcg_at_k(list(dict.fromkeys(relevant_ids)), relevant_ids, k)
    if ideal == 0.0:
        return 1.0
    return dcg_at_k(ranked_ids, relevant_ids, k) / ideal


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean, with an empty set scoring 1.0 rather than 0.0 or NaN.

    Every gate here is "at least X", and a language with no applicable cases has not failed
    anything — reporting 0.0 would make an absent measurement look like a regression, which is
    the one thing a relevance report must never do.
    """
    if not values:
        return 1.0
    return sum(values) / len(values)
