from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.application.search.normalizer import Language

CUT_FLOOR = "below_floor"
CUT_GAP = "score_gap"
CUT_UNSCORED = "unscored"
CUT_MAX_RESULTS = "max_results"


@dataclass(frozen=True, slots=True)
class RelevanceCutoff:
    floor: float
    gap_ratio: float
    max_results: int

    @property
    def enabled(self) -> bool:
        return self.floor > 0.0 or self.gap_ratio > 0.0


@dataclass(frozen=True, slots=True)
class CutoffOutcome:
    product_ids: list[int]
    dropped: int
    reason: str | None


def apply_cutoff(
    product_ids: Sequence[int],
    scores: Sequence[float | None] | None,
    cutoff: RelevanceCutoff,
) -> CutoffOutcome:
    ids = list(product_ids)
    if not cutoff.enabled or scores is None or len(scores) != len(ids):
        return CutoffOutcome(ids, dropped=0, reason=None)

    kept: list[int] = []
    previous: float | None = None
    reason: str | None = None

    for product_id, score in zip(ids, scores, strict=True):
        if score is None:
            reason = CUT_UNSCORED
            break
        if score < cutoff.floor:
            reason = CUT_FLOOR
            break
        if previous is not None and cutoff.gap_ratio > 0.0 and score < previous * cutoff.gap_ratio:
            reason = CUT_GAP
            break
        kept.append(product_id)
        previous = score
        if cutoff.max_results and len(kept) >= cutoff.max_results:
            reason = CUT_MAX_RESULTS if len(kept) < len(ids) else None
            break

    return CutoffOutcome(kept, dropped=len(ids) - len(kept), reason=reason)


def resolve_cutoff(
    language: Language, *, floor_en: float, floor_ar: float, gap_ratio: float, max_results: int
) -> RelevanceCutoff:
    return RelevanceCutoff(
        floor=floor_ar if language in ("ar", "mixed") else floor_en,
        gap_ratio=gap_ratio,
        max_results=max_results,
    )
