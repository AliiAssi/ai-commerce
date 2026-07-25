from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Field descriptions double as LLM-facing tool schema docs — write them for the model.


class ProductSearchParams(BaseModel):
    query: str | None = Field(
        default=None,
        description="Full-text search over product names and descriptions, "
        "e.g. 'waterproof tent' or 'noise cancelling headphones'.",
    )
    category_slug: str | None = Field(
        default=None,
        description="Limit results to one category by its slug (get slugs from list_categories).",
    )
    min_price: float | None = Field(
        default=None, ge=0, description="Only products costing at least this many USD."
    )
    max_price: float | None = Field(
        default=None, ge=0, description="Only products costing at most this many USD."
    )
    in_stock_only: bool = Field(
        default=False, description="Only products that are currently in stock."
    )
    sort: Literal["relevance", "newest", "price_asc", "price_desc", "rating"] = Field(
        default="rating",
        description="Result order: 'rating' (best rated first), 'price_asc', 'price_desc', "
        "'newest', or 'relevance' (only meaningful together with query).",
    )
    page: int = Field(default=1, ge=1, description="1-based results page.")
    page_size: int = Field(default=10, ge=1, le=20, description="Results per page (max 20).")
