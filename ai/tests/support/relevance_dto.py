from __future__ import annotations

from pydantic import BaseModel, Field

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
FAILURE_TOO_MANY = "too_many_results"
FAILURE_IRRELEVANT = "irrelevant_present"


class CaseResultDTO(BaseModel):
    model_config = {"frozen": True}

    case_id: str
    language: str
    source: str
    query: str

    passed: bool
    failures: list[str] = Field(default_factory=list)
    detail: list[str] = Field(default_factory=list)

    reciprocal_rank: float | None = None
    recall_at_k: float | None = None
    ndcg_at_10: float | None = None
    precision_at_3: float | None = None
    precision_at_5: float | None = None
    returned_count: int = 0
    filters_correct: bool | None = None
    exact_name_hit: bool | None = None

    returned: list[str] = Field(default_factory=list)
    total: int = 0
    mode: str | None = None
    degraded_reason: str | None = None


class LanguageScoreDTO(BaseModel):
    model_config = {"frozen": True}

    language: str
    cases: int
    passed: int

    mrr: float
    recall_at_5: float
    ndcg_at_10: float
    precision_at_3: float
    precision_at_5: float
    filter_precision: float
    exact_name_rate: float

    @property
    def pass_rate(self) -> float:
        return 1.0 if not self.cases else self.passed / self.cases


class RelevanceReportDTO(BaseModel):
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
