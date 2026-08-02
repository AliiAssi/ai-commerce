from __future__ import annotations

from app.application.search.relevance import (
    CUT_FLOOR,
    CUT_GAP,
    CUT_MAX_RESULTS,
    CUT_UNSCORED,
    RelevanceCutoff,
    apply_cutoff,
    resolve_cutoff,
)

CUTOFF = RelevanceCutoff(floor=0.15, gap_ratio=0.35, max_results=12)
FLOOR_ONLY = RelevanceCutoff(floor=0.15, gap_ratio=0.0, max_results=12)
GAP_ONLY = RelevanceCutoff(floor=0.0, gap_ratio=0.35, max_results=12)
OFF = RelevanceCutoff(floor=0.0, gap_ratio=0.0, max_results=12)


def test_the_irrelevant_tail_is_dropped_at_the_floor():
    outcome = apply_cutoff([1, 2, 3, 4, 5], [0.94, 0.71, 0.44, 0.03, 0.001], FLOOR_ONLY)

    assert outcome.product_ids == [1, 2, 3]
    assert outcome.dropped == 2
    assert outcome.reason == CUT_FLOOR


def test_one_strong_match_may_come_back_alone():
    outcome = apply_cutoff([1, 2, 3], [0.97, 0.22, 0.19], GAP_ONLY)

    assert outcome.product_ids == [1]
    assert outcome.reason == CUT_GAP


def test_a_gently_decaying_run_survives_the_gap_rule():
    outcome = apply_cutoff([1, 2, 3, 4], [0.90, 0.80, 0.70, 0.61], CUTOFF)

    assert outcome.product_ids == [1, 2, 3, 4]
    assert outcome.dropped == 0
    assert outcome.reason is None


def test_the_gap_is_measured_against_the_previous_kept_score():
    outcome = apply_cutoff([1, 2, 3], [0.90, 0.40, 0.30], GAP_ONLY)

    assert outcome.product_ids == [1, 2, 3], "0.40 >= 0.90*0.35 and 0.30 >= 0.40*0.35"


def test_nothing_clearing_the_floor_returns_an_empty_result():
    outcome = apply_cutoff([1, 2, 3], [0.04, 0.02, 0.001], FLOOR_ONLY)

    assert outcome.product_ids == []
    assert outcome.dropped == 3


def test_candidates_beyond_the_scoring_window_are_not_vouched_for():
    outcome = apply_cutoff([1, 2, 3], [0.90, 0.80, None], CUTOFF)

    assert outcome.product_ids == [1, 2]
    assert outcome.reason == CUT_UNSCORED


def test_the_result_count_is_capped():
    scores = [0.9 - i * 0.01 for i in range(20)]
    outcome = apply_cutoff(list(range(20)), scores, RelevanceCutoff(0.15, 0.35, max_results=5))

    assert len(outcome.product_ids) == 5
    assert outcome.reason == CUT_MAX_RESULTS


def test_hitting_the_cap_on_the_last_candidate_is_not_a_cut():
    outcome = apply_cutoff([1, 2], [0.9, 0.8], RelevanceCutoff(0.15, 0.35, max_results=2))

    assert outcome.product_ids == [1, 2]
    assert outcome.reason is None


def test_a_disabled_cutoff_passes_everything_through():
    outcome = apply_cutoff([1, 2, 3], [0.9, 0.01, 0.0001], OFF)

    assert outcome.product_ids == [1, 2, 3]
    assert outcome.dropped == 0


def test_missing_scores_leave_the_order_untouched():
    outcome = apply_cutoff([1, 2, 3], None, CUTOFF)

    assert outcome.product_ids == [1, 2, 3]
    assert outcome.reason is None


def test_a_short_score_list_is_not_trusted_to_filter():
    outcome = apply_cutoff([1, 2, 3], [0.9], CUTOFF)

    assert outcome.product_ids == [1, 2, 3]
    assert outcome.dropped == 0


def test_arabic_and_mixed_queries_get_their_own_floor():
    kwargs = {"floor_en": 0.15, "floor_ar": 0.10, "gap_ratio": 0.35, "max_results": 12}

    assert resolve_cutoff("en", **kwargs).floor == 0.15
    assert resolve_cutoff("ar", **kwargs).floor == 0.10
    assert resolve_cutoff("mixed", **kwargs).floor == 0.10


def test_a_zero_floor_and_zero_gap_is_the_off_switch():
    assert not RelevanceCutoff(0.0, 0.0, 12).enabled
    assert RelevanceCutoff(0.15, 0.0, 12).enabled
    assert RelevanceCutoff(0.0, 0.35, 12).enabled
