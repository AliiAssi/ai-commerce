from __future__ import annotations

from pydantic import BaseModel, Field

# Failure codes. Codes rather than prose so a report can be diffed between two runs and the
# difference read at a glance — which is the whole point of scoring a fixed corpus.
FAILURE_FIRST = "wrong_first"
FAILURE_NOT_FIRST = "should_not_be_first"
FAILURE_MISSING = "missing_required"
FAILURE_EXCLUDED = "excluded_present"
FAILURE_FILTERS = "wrong_filters"
FAILURE_INFERRED = "wrong_inferred"
FAILURE_EMPTY = "unexpected_results"
FAILURE_ERROR_EXPECTED = "expected_rejection"
FAILURE_ERROR_UNEXPECTED = "unexpected_rejection"
FAILURE_UNKNOWN_PRODUCT = "unknown_product"


class CaseResultDTO(BaseModel):
    """What one judged query actually did."""

    model_config = {"frozen": True}

    case_id: str
    language: str
    source: str
    query: str

    passed: bool
    failures: list[str] = Field(default_factory=list)
    detail: list[str] = Field(default_factory=list)

    # Per-case metric contributions. None means the case does not participate in that gate.
    reciprocal_rank: float | None = None
    recall_at_k: float | None = None
    ndcg_at_10: float | None = None
    filters_correct: bool | None = None
    exact_name_hit: bool | None = None

    returned: list[str] = Field(default_factory=list)
    total: int = 0
    mode: str | None = None
    degraded_reason: str | None = None


class LanguageScoreDTO(BaseModel):
    """§15's gates, computed for one language. Reported separately per §18.1 step 4."""

    model_config = {"frozen": True}

    language: str
    cases: int
    passed: int

    mrr: float
    recall_at_5: float
    ndcg_at_10: float
    filter_precision: float
    exact_name_rate: float

    @property
    def pass_rate(self) -> float:
        return 1.0 if not self.cases else self.passed / self.cases


class RelevanceReportDTO(BaseModel):
    """One scoring run over the corpus.

    `label` names what was being scored — a baseline, or a candidate embedding model — because a
    report that cannot say what produced it is not evidence of anything.

    `retrieval_path` is there for the same reason and was added after a run mislabelled itself:
    the coverage gate is process state, so a scorer that never refreshed it silently measured
    §12's step 4 while the report claimed step 3. Two rungs, two different sets of results, and
    nothing in the numbers to tell them apart.
    """

    model_config = {"frozen": True}

    label: str
    corpus_version: int
    scored_cases: int
    draft_cases: int
    retrieval_path: str = "unknown"
    index_coverage: str | None = None

    overall: LanguageScoreDTO
    by_language: list[LanguageScoreDTO] = Field(default_factory=list)
    results: list[CaseResultDTO] = Field(default_factory=list)
    drafts: list[CaseResultDTO] = Field(default_factory=list)

    gate_failures: list[str] = Field(default_factory=list)

    @property
    def gates_pass(self) -> bool:
        return not self.gate_failures
