from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

# `relevance` is only meaningful with a query; §9.1 makes it the conditional default when `q`
# is present and `newest` the default without one. The admin catalog never uses it — §9.2 keeps
# admin search lexical and independent of any provider.
SortOption = Literal["relevance", "newest", "price_asc", "price_desc", "rating"]

# §9.2's search metadata. These mirror the AI service's enums; web does not invent values, it
# reports what retrieval told it, or fills them in itself when it served the fallback.
SearchMode = Literal["browse", "filters_only", "hybrid_reranked", "hybrid", "lexical"]
# `search_unavailable` extends §9.2's four values: that section predates the AI service owning
# retrieval, when search could not be unreachable because it was in-process. Reporting an
# outage as `feature_disabled` would misinform §13's analytics about why searches degraded.
DegradedReason = Literal[
    "embedding_unavailable",
    "reranker_unavailable",
    "index_incomplete",
    "feature_disabled",
    "search_unavailable",
]
InferredName = Literal["category", "origin", "min_price", "max_price", "in_stock_only", "sort"]


class CategoryDTO(BaseModel):
    id: int
    name: str
    slug: str
    product_count: int = 0


class ProductDTO(BaseModel):
    id: int
    name: str
    description: str
    origin: str | None
    price: Decimal
    stock: int
    image_url: str | None
    rating_avg: Decimal
    review_count: int
    is_archived: bool
    category_id: int
    category_name: str
    category_slug: str
    created_at: datetime


class SearchMetadataDTO(BaseModel):
    """The additive `search` object in §9.2. Absent entirely for non-search requests."""

    query: str
    language: str
    mode: SearchMode
    reranked: bool = False
    effective_sort: SortOption
    inferred_filters: dict[str, str] = {}
    ignored_inferred: list[str] = []
    degraded: bool = False
    # Always null when `degraded` is false, and never carries a provider name, exception text,
    # or status code (§9.2).
    degraded_reason: DegradedReason | None = None


class ProductListDTO(BaseModel):
    items: list[ProductDTO]
    total: int
    page: int
    page_size: int
    search: SearchMetadataDTO | None = None


class ProductSearchParams(BaseModel):
    q: str | None = None
    category_slug: str | None = None
    # Explicit filters from the URL or sidebar. These always beat anything inferred from `q`.
    origin: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock_only: bool | None = None
    # None means "the client did not choose", which is what lets §9.1's conditional default
    # work: relevance with a query, newest without one. A literal "newest" cannot express that.
    sort: SortOption | None = None
    page: int = 1
    page_size: int = 12
    ignore_inferred: tuple[str, ...] = ()
    include_archived: bool = False
    archived_only: bool = False
    max_stock: int | None = None

    @property
    def effective_sort(self) -> SortOption:
        if self.sort is not None:
            return self.sort
        return "relevance" if (self.q or "").strip() else "newest"


class ProductStockDTO(BaseModel):
    id: int
    name: str
    price: Decimal
    stock: int
    is_archived: bool


class ProductCreateDTO(BaseModel):
    name: str
    description: str
    origin: str | None = None
    price: Decimal
    stock: int
    category_id: int
    image_url: str | None = None


class ProductUpdateDTO(BaseModel):
    name: str | None = None
    description: str | None = None
    origin: str | None = None
    price: Decimal | None = None
    category_id: int | None = None
    image_url: str | None = None
