from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

# Error codes stored in ai_search_index_jobs.last_error_code. Codes, never provider messages:
# operators read these rows, and §10.3 requires diagnosis without leaking secrets.
ERROR_DATABASE = "database_error"
ERROR_UNEXPECTED = "unexpected_error"


def embedding_error_code(code: str) -> str:
    """`EmbeddingError.code` as a job error code.

    Prefixed rather than stored raw so `failed_jobs` reads unambiguously: "unauthorized" alone
    beside "database_error" does not say which system rejected what. §11 rule 6 exists so an
    operator can tell a provider outage from a schema problem at a glance.
    """
    return f"embedding_{code}"


class ClaimedJobDTO(BaseModel):
    """A leased job. `attempts` is the count *before* this attempt, which is what the backoff
    schedule is a function of — carrying it out of the claim keeps the delay computed in one
    place instead of once in Python and once in an UPDATE."""

    model_config = {"frozen": True}

    product_id: int
    attempts: int


class StoredVectorDTO(BaseModel):
    """What one vector slot currently holds for a product, if anything.

    Read alongside the catalog fields so the worker can tell which halves of a document are
    actually stale. Without it, a drift caused only by a fallback provider being reconfigured
    would re-embed the primary column too — paying a provider call to rewrite a vector that was
    already correct.
    """

    model_config = {"frozen": True}

    present: bool = False
    embedding_model: str | None = None
    embedding_dimensions: int | None = None

    def matches(self, model: str | None, dimensions: int | None) -> bool:
        return (
            self.present
            and self.embedding_model == model
            and self.embedding_dimensions == dimensions
        )


class CatalogRowDTO(BaseModel):
    """One product's semantic fields, read live from the catalog the web service owns.

    The `stored_*` fields describe what the index already holds for this product, not what the
    catalog says. They are what turns "this product is drifted" into "these halves of it are".
    """

    model_config = {"frozen": True}

    product_id: int
    name: str
    category_name: str
    origin: str | None = None
    description: str

    # None means no document exists yet — which is the case that must still be written when an
    # embedding provider is down, or the product would be invisible to lexical search too.
    stored_hash: str | None = None
    stored_vectors: dict[str, StoredVectorDTO] = Field(default_factory=dict)

    @property
    def is_indexed(self) -> bool:
        return self.stored_hash is not None

    def vector(self, slot: str) -> StoredVectorDTO:
        return self.stored_vectors.get(slot, StoredVectorDTO())


class SearchDocumentDTO(BaseModel):
    """A built document, ready to store.

    It carries the source fields as well as the assembled text: the stored tsvectors are built
    per field so §7.4's ranking can weight a product name above a category name (setweight A/B/D),
    which is impossible from the flattened text alone.
    """

    model_config = {"frozen": True}

    product_id: int
    name: str
    category_name: str
    origin: str | None = None
    description: str

    document_text: str
    document_hash: str
    document_version: int


@dataclass(frozen=True, slots=True)
class EmbeddedSlot:
    """One slot's freshly produced vectors, keyed by product id.

    A dataclass rather than a pydantic model, deliberately: this carries tens of thousands of
    floats per batch straight from the provider to the driver, and validating each one would be
    the most expensive thing in the indexing path while proving nothing `validated_batch` has not
    already checked at the boundary where the data was untrusted.

    Keyed by product id rather than positional, because the batch sent to the provider excludes
    products whose slot was already current — so position in the response and position in the
    claimed batch are not the same list, and pairing them by index is exactly how vectors end up
    against the wrong products.
    """

    model: str
    dimensions: int
    vectors: dict[int, tuple[float, ...]] = field(default_factory=dict)


class VectorExpectationDTO(BaseModel):
    """What one slot's stored vectors must agree with for the index to count as current.

    Configuration crossing into the repository as a value rather than as a client, so the SQL
    that finds drifted rows stays ignorant of providers, breakers and HTTP. An empty list of
    these means "no vector conditions at all", which is exactly the behaviour before this phase
    and the behaviour when no provider is configured.
    """

    model_config = {"frozen": True}

    slot: str
    embedding_model: str
    embedding_dimensions: int


class IndexCoverageDTO(BaseModel):
    """How much of the active catalog currently has a document, and a current vector per slot.

    Two different readinesses, measured in one scan so they cannot disagree. Document coverage
    gates §12's step 3 against step 4; vector coverage gates the semantic leg. Conflating them
    would either switch the lexical leg off because an embedding provider was down, or run the
    semantic leg over a half-filled column — §12 lists that second one as its own fallback
    trigger.
    """

    model_config = {"frozen": True}

    active_products: int
    documents: int
    # slot -> products whose stored vector matches the configured model and dimensions.
    embedded: dict[str, int] = Field(default_factory=dict)

    @property
    def ratio(self) -> float:
        if self.active_products <= 0:
            return 0.0
        return self.documents / self.active_products

    @property
    def missing(self) -> int:
        return max(self.active_products - self.documents, 0)

    def embedded_ratio(self, slot: str) -> float:
        if self.active_products <= 0:
            return 0.0
        return self.embedded.get(slot, 0) / self.active_products


class FailedJobDTO(BaseModel):
    """A job that has exhausted its attempts and is waiting for an operator (§11 rule 6)."""

    model_config = {"frozen": True}

    product_id: int
    attempts: int
    last_error_code: str | None = None


class SweepReportDTO(BaseModel):
    """What one hash-drift sweep did (§0.4)."""

    model_config = {"frozen": True}

    pruned: int = 0
    enqueued: int = 0
    coverage: IndexCoverageDTO


class IndexRunReportDTO(BaseModel):
    """What one batch — or a whole CLI drain — produced."""

    model_config = {"frozen": True}

    claimed: int = 0
    indexed: int = 0
    failed: int = 0
    # Vectors written, by slot. Separate from `indexed` because a batch can store documents while
    # an embedding provider is down, and a report that showed only "16 indexed" would hide it.
    embedded: dict[str, int] = Field(default_factory=dict)
