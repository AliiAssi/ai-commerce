from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.search_dto import (
    DegradedReason,
    ExplicitFilters,
    SearchMode,
    SearchQuery,
    SearchResultDTO,
    SortKey,
)
from app.application.search.normalizer import Language

# The internal search contract. Not a browser-facing surface: the web service is the only
# caller, and it authenticates with INTERNAL_API_KEY like the chat endpoint does.


class SearchRequest(BaseModel):
    # An unknown field is a rejected request, not an ignored one. Found by probing the live
    # endpoint: `catgory`, `maxprice` and a wrongly nested `explicit` object all returned 200
    # with results that silently ignored the filter. That is the request-side of §12's rule
    # about half-populated responses — a page that quietly dropped a constraint looks like an
    # answer, and would read as a relevance bug rather than a contract one.
    #
    # Safe because this endpoint has exactly one caller: web's `_search_payload` sends these ten
    # fields and nothing else, and the E2E suite exercises that path on every run.
    model_config = ConfigDict(extra="forbid")

    # §5.1 caps the query at 200 characters; enforcing it here means the parser never sees a
    # longer one regardless of who calls (§14.4's "limits enforced at the API edge").
    q: str = Field(default="", max_length=200)

    category: str | None = Field(default=None, max_length=100)
    origin: str | None = Field(default=None, max_length=100)
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    in_stock_only: bool | None = None
    sort: SortKey | None = None

    ignore_inferred: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=100)

    def to_query(self) -> SearchQuery:
        return SearchQuery(
            q=self.q,
            explicit=ExplicitFilters(
                category_slug=self.category,
                origin=self.origin,
                min_price=self.min_price,
                max_price=self.max_price,
                in_stock_only=self.in_stock_only,
                sort=self.sort,
            ),
            # Unknown names are dropped downstream without error, per §9.1.
            ignore_inferred=tuple(self.ignore_inferred),
            page=self.page,
            page_size=self.page_size,
        )


class SearchResponse(BaseModel):
    """Ordered ids plus §9.2's metadata. Carries no scores — §7.4 keeps those internal."""

    product_ids: list[int]
    total: int
    page: int
    page_size: int

    query: str
    language: Language
    mode: SearchMode
    reranked: bool
    effective_sort: SortKey
    inferred_filters: dict[str, str]
    ignored_inferred: list[str]
    degraded: bool
    degraded_reason: DegradedReason | None

    parser_version: str
    lexicon_version: int
    ranker_version: str

    @classmethod
    def from_dto(cls, dto: SearchResultDTO) -> SearchResponse:
        return cls.model_validate(dto, from_attributes=True)
