from __future__ import annotations

from collections.abc import Sequence
from math import log2


def reciprocal_rank(ranked_ids: Sequence[int], target_id: int) -> float:
    for position, product_id in enumerate(ranked_ids, start=1):
        if product_id == target_id:
            return 1.0 / position
    return 0.0


def recall_at_k(ranked_ids: Sequence[int], required_ids: Sequence[int], k: int) -> float:
    if not required_ids:
        return 1.0
    window = set(ranked_ids[:k])
    found = sum(1 for product_id in required_ids if product_id in window)
    return found / len(required_ids)


def precision_at_k(ranked_ids: Sequence[int], relevant_ids: Sequence[int], k: int) -> float:
    window = ranked_ids[:k]
    if not window:
        return 1.0
    relevant = set(relevant_ids)
    return sum(1 for product_id in window if product_id in relevant) / len(window)


def dcg_at_k(ranked_ids: Sequence[int], relevant_ids: Sequence[int], k: int) -> float:
    relevant = set(relevant_ids)
    return sum(
        1.0 / log2(position + 1)
        for position, product_id in enumerate(ranked_ids[:k], start=1)
        if product_id in relevant
    )


def ndcg_at_k(ranked_ids: Sequence[int], relevant_ids: Sequence[int], k: int) -> float:
    if not relevant_ids:
        return 1.0
    ideal = dcg_at_k(list(dict.fromkeys(relevant_ids)), relevant_ids, k)
    if ideal == 0.0:
        return 1.0
    return dcg_at_k(ranked_ids, relevant_ids, k) / ideal


def mean(values: Sequence[float]) -> float:
    if not values:
        return 1.0
    return sum(values) / len(values)
