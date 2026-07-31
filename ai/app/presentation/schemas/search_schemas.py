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


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
            ignore_inferred=tuple(self.ignore_inferred),
            page=self.page,
            page_size=self.page_size,
        )


class SearchResponse(BaseModel):
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
