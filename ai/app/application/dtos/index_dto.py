from __future__ import annotations

from pydantic import BaseModel

# Error codes stored in ai_search_index_jobs.last_error_code. Codes, never provider messages:
# operators read these rows, and §10.3 requires diagnosis without leaking secrets.
ERROR_DATABASE = "database_error"
ERROR_UNEXPECTED = "unexpected_error"


class ClaimedJobDTO(BaseModel):
    """A leased job. `attempts` is the count *before* this attempt, which is what the backoff
    schedule is a function of — carrying it out of the claim keeps the delay computed in one
    place instead of once in Python and once in an UPDATE."""

    model_config = {"frozen": True}

    product_id: int
    attempts: int


class CatalogRowDTO(BaseModel):
    """One product's semantic fields, read live from the catalog the web service owns."""

    model_config = {"frozen": True}

    product_id: int
    name: str
    category_name: str
    origin: str | None = None
    description: str


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


class IndexCoverageDTO(BaseModel):
    """How much of the active catalog currently has a document."""

    model_config = {"frozen": True}

    active_products: int
    documents: int

    @property
    def ratio(self) -> float:
        if self.active_products <= 0:
            return 0.0
        return self.documents / self.active_products

    @property
    def missing(self) -> int:
        return max(self.active_products - self.documents, 0)


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
