from __future__ import annotations

import pytest

from app.application.search.metrics import (
    dcg_at_k,
    mean,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestReciprocalRank:
    def test_first_place_scores_one(self):
        assert reciprocal_rank([7, 8, 9], 7) == 1.0

    def test_later_places_decay_by_rank(self):
        assert reciprocal_rank([8, 7, 9], 7) == 0.5
        assert reciprocal_rank([8, 9, 7], 7) == pytest.approx(1 / 3)

    def test_an_absent_target_scores_zero(self):
        # Not None. §15's MRR gate averages over the "MUST rank first" cases, and a miss has to
        # pull that average down rather than quietly leave the case out of it.
        assert reciprocal_rank([8, 9], 7) == 0.0


class TestRecall:
    def test_everything_found_inside_the_window(self):
        assert recall_at_k([1, 2, 3, 4, 5], [2, 4], 5) == 1.0

    def test_a_product_past_the_window_does_not_count(self):
        # The window is the case's own top_k. A required product at rank 9 is a miss even though
        # it was returned — §15 states positions, not membership.
        assert recall_at_k([1, 2, 3, 4, 5, 6], [6], 5) == 0.0

    def test_partial_credit(self):
        assert recall_at_k([1, 2, 3], [2, 9], 3) == 0.5

    def test_requiring_nothing_scores_one(self):
        # A case that requires no particular product cannot lower recall. Scoring it 0.0 would
        # drag the aggregate down for cases that were never about recall at all.
        assert recall_at_k([1, 2], [], 5) == 1.0


class TestNdcg:
    def test_perfect_order_scores_one(self):
        assert ndcg_at_k([1, 2, 3], [1, 2], 10) == pytest.approx(1.0)

    def test_relevant_results_lower_down_score_less(self):
        good = ndcg_at_k([1, 2, 9, 9], [1, 2], 10)
        worse = ndcg_at_k([9, 9, 1, 2], [1, 2], 10)
        assert good > worse

    def test_the_discount_is_logarithmic(self):
        # Position 1 counts fully, position 3 by 1/log2(4) = 0.5. Pinned because phase 7 compares
        # a reranked order against the pre-rerank one with this exact arithmetic.
        assert dcg_at_k([9, 9, 1], [1], 10) == pytest.approx(0.5)

    def test_nothing_relevant_scores_one_rather_than_zero(self):
        assert ndcg_at_k([1, 2], [], 10) == 1.0


class TestMean:
    def test_ordinary_mean(self):
        assert mean([1.0, 0.0]) == 0.5

    def test_no_measurements_scores_one(self):
        # Every §15 gate is "at least X". A language with no applicable cases has not failed
        # anything, and reporting 0.0 would make an absent measurement look like a regression.
        assert mean([]) == 1.0
