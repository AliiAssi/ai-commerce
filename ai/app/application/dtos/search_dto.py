from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.application.search.normalizer import Language

SortKey = Literal["relevance", "newest", "price_asc", "price_desc", "rating"]

SearchMode = Literal["browse", "filters_only", "hybrid_reranked", "hybrid", "lexical"]

DegradedReason = Literal[
    "embedding_unavailable",
    "reranker_unavailable",
    "index_incomplete",
    "feature_disabled",
    "search_unavailable",
]

InferredName = Literal["category", "origin", "min_price", "max_price", "in_stock_only", "sort"]

INFERRED_NAMES: tuple[InferredName, ...] = (
    "category",
    "origin",
    "min_price",
    "max_price",
    "in_stock_only",
    "sort",
)


class SearchIntent(BaseModel):
    model_config = {"frozen": True}

    original_query: str
    normalized_query: str
    language: Language
    semantic_text: str

    inferred_category_slug: str | None = None
    inferred_origin: str | None = None
    inferred_min_price: Decimal | None = None
    inferred_max_price: Decimal | None = None
    inferred_in_stock_only: bool | None = None
    inferred_sort: SortKey | None = None

    parser_version: str
    lexicon_version: int


class ExplicitFilters(BaseModel):
    category_slug: str | None = None
    origin: str | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    in_stock_only: bool | None = None
    sort: SortKey | None = None


class EffectiveFilters(BaseModel):
    model_config = {"frozen": True}

    category_slug: str | None = None
    origins: tuple[str, ...] = ()
    origin_key: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock_only: bool = False
    sort: SortKey = "relevance"

    inferred_filters: dict[str, str] = Field(default_factory=dict)
    ignored_inferred: tuple[str, ...] = ()

    @property
    def has_filters(self) -> bool:
        return bool(
            self.category_slug
            or self.origins
            or self.min_price is not None
            or self.max_price is not None
            or self.in_stock_only
        )


class SearchCandidate(BaseModel):
    product_id: int
    rrf_score: float
    semantic_rank: int | None = None
    lexical_rank: int | None = None
    trigram_rank: int | None = None
    exact_name_match: bool = False


class QueryVectorDTO(BaseModel):
    model_config = {"frozen": True}

    values: tuple[float, ...]
    slot: str
    embedding_model: str
    dimensions: int


class RetrievalRequest(BaseModel):
    model_config = {"frozen": True}

    semantic_text: str
    normalized_query: str
    filters: EffectiveFilters
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=100)
    query_vector: QueryVectorDTO | None = None


class SearchQuery(BaseModel):
    model_config = {"frozen": True}

    q: str = Field(default="", max_length=200)
    explicit: ExplicitFilters = Field(default_factory=ExplicitFilters)
    ignore_inferred: tuple[str, ...] = ()
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=100)


class SearchResultDTO(BaseModel):
    product_ids: list[int]
    total: int
    page: int
    page_size: int

    query: str
    language: Language
    mode: SearchMode
    reranked: bool = False
    effective_sort: SortKey
    inferred_filters: dict[str, str] = Field(default_factory=dict)
    ignored_inferred: list[str] = Field(default_factory=list)
    degraded: bool = False
    degraded_reason: DegradedReason | None = None

    parser_version: str
    lexicon_version: int
    ranker_version: str


class CatalogLexiconDTO(BaseModel):
    category_slugs: list[str]
    origins: list[str]


class RetrievalResult(BaseModel):
    product_ids: list[int]
    total: int
    page: int
    page_size: int
    semantic_hits: int = 0
    lexical_hits: int = 0
    trigram_hits: int = 0
    semantic_used: bool = False
    filters_only: bool = False
    documents_used: bool = False
