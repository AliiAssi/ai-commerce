from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.application.search.normalizer import Language

SortKey = Literal["relevance", "newest", "price_asc", "price_desc", "rating"]

# §9.2. `lexical` deliberately covers both "the provider failed" and "the feature is off": a
# client cannot act on the difference, and splitting them would publish operational state in a
# public contract. The distinction survives in `degraded_reason`, which is where it is useful.
SearchMode = Literal["browse", "filters_only", "hybrid_reranked", "hybrid", "lexical"]

# A closed, non-sensitive enum. It must never carry a provider name, exception text, or status
# code (§9.2).
#
# `search_unavailable` is an addition to §9.2's four values. That section was written while the
# web service owned retrieval, when "the search service is unreachable" could not happen — it
# was the same process. The ownership reversal made it a real and routine failure mode, and
# folding it into `feature_disabled` would tell §13's analytics that a configuration choice was
# made every time the AI service was merely asleep.
DegradedReason = Literal[
    "embedding_unavailable",
    "reranker_unavailable",
    "index_incomplete",
    "feature_disabled",
    "search_unavailable",
]

# The names a shopper can suppress with ?ignore_inferred=... (§9.1). They are the inference
# names, not the SQL column names, because that is what the chip in the UI is labelled with.
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
    """What the parser understood. §6's DTO, plus the lexicon version behind it.

    This is the parser's complete reading of the query. It is deliberately produced *before*
    `ignore_inferred` is applied: §5.2.1 requires suppression to happen when the intent is
    reduced to effective filters, never by skipping parsing, so that a suppressed inference is
    still knowable — it just is not applied and is not reported.
    """

    model_config = {"frozen": True}

    original_query: str
    normalized_query: str
    language: Language
    # What is left after price, stock and sort phrases are removed. Category and origin words
    # stay: they are descriptive, and §5.2.1 requires "from Beirut" to keep influencing rank
    # even when the Beirut filter itself has been dropped.
    semantic_text: str

    inferred_category_slug: str | None = None
    inferred_origin: str | None = None  # canonical place key, e.g. "north-lebanon"
    inferred_min_price: Decimal | None = None
    inferred_max_price: Decimal | None = None
    inferred_in_stock_only: bool | None = None
    inferred_sort: SortKey | None = None

    parser_version: str
    lexicon_version: int


class ExplicitFilters(BaseModel):
    """Filters the shopper set through the URL or the sidebar. These always win (§5.2)."""

    category_slug: str | None = None
    origin: str | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    in_stock_only: bool | None = None
    sort: SortKey | None = None


class EffectiveFilters(BaseModel):
    """The filters actually applied, plus what to tell the shopper about them."""

    model_config = {"frozen": True}

    category_slug: str | None = None
    # Literal products.origin strings, expanded from the place hierarchy. Empty means no origin
    # filter; a place that resolves to nothing would be a lexicon bug caught at startup.
    origins: tuple[str, ...] = ()
    origin_key: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock_only: bool = False
    sort: SortKey = "relevance"

    # Reported to the client as search.inferred_filters. Holds every inference the parser made
    # and the shopper did not suppress — including one an explicit filter overrode, which §15.3
    # requires to be reported but not applied.
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
    """One product's retrieval scores. Internal only — §7.4 keeps scores out of public JSON."""

    product_id: int
    rrf_score: float
    semantic_rank: int | None = None
    lexical_rank: int | None = None
    trigram_rank: int | None = None
    exact_name_match: bool = False


class QueryVectorDTO(BaseModel):
    """One query embedding, and the column it is allowed to be compared against.

    The slot travels with the vector rather than being looked up at the point of use, because the
    two must never come apart. Vectors from different models occupy different spaces: comparing
    this one against the wrong column returns neighbours that are not merely worse but arbitrary,
    and nothing downstream — not the relevance floor, not RRF, not the reranker — can tell that
    from a good answer.
    """

    model_config = {"frozen": True}

    values: tuple[float, ...]
    slot: str
    embedding_model: str
    dimensions: int


class RetrievalRequest(BaseModel):
    """Everything the repository needs to fuse candidates and return one page."""

    model_config = {"frozen": True}

    # What the ranker matches on, after constraint phrases were removed. Empty means the query
    # was nothing but constraints, and retrieval reduces to a filtered browse (§7.2).
    semantic_text: str
    # The whole normalized query, used only for the exact-product-name rule in §7.4. It is not
    # the semantic text: "Baladi Extra Virgin Olive Oil" must match the product of that name
    # even though the parser also read a category out of it.
    normalized_query: str
    filters: EffectiveFilters
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=100)
    # Absent means no semantic leg for this query — the feature is off, the provider failed, the
    # slot's column is not populated enough to read, or the query is pure constraints. Retrieval
    # then behaves exactly as it did in phase 4, which is §12's step 3.
    query_vector: QueryVectorDTO | None = None


class SearchQuery(BaseModel):
    """One search request as the AI service receives it, already validated at the edge."""

    model_config = {"frozen": True}

    q: str = Field(default="", max_length=200)
    explicit: ExplicitFilters = Field(default_factory=ExplicitFilters)
    ignore_inferred: tuple[str, ...] = ()
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=100)


class SearchResultDTO(BaseModel):
    """Ordered product ids plus the §9.2 metadata the web service reports to the client.

    Ids rather than products, deliberately. The web service owns the catalog and its public
    product contract; having it hydrate its own rows keeps that contract defined in exactly one
    place, keeps the payload small, and makes it impossible for a product archived between the
    two queries to leak into a response.
    """

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

    # §14.5: a ranking change that cannot be attributed to a version is not measurable.
    parser_version: str
    lexicon_version: int
    ranker_version: str


class CatalogLexiconDTO(BaseModel):
    """The catalog terms the alias file has to keep describing (§6's startup validation)."""

    category_slugs: list[str]
    origins: list[str]


class RetrievalResult(BaseModel):
    """A page of product IDs in final order, plus how they were found."""

    product_ids: list[int]
    total: int
    page: int
    page_size: int
    # Which legs returned anything. The caller derives search.mode from this rather than the
    # repository asserting a mode it cannot fully know (§9.2).
    semantic_hits: int = 0
    lexical_hits: int = 0
    trigram_hits: int = 0
    # Whether the semantic leg ran at all, which is not the same as whether it matched anything.
    # A leg that ran and found nothing above the similarity floor is a working semantic search
    # reporting an honest empty; a leg that never ran is a degradation, and §9.2 needs the two
    # told apart to pick a mode.
    semantic_used: bool = False
    # True when there was no semantic text and this was a filtered browse.
    filters_only: bool = False
    # Which rung of §12's ladder the lexical leg actually ran on: this service's documents
    # (step 3) or web's products.search_vector (step 4). Reported rather than inferred, because
    # the difference is index coverage at the moment of the query and nothing else can see it.
    documents_used: bool = False
