from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

ERROR_DATABASE = "database_error"
ERROR_UNEXPECTED = "unexpected_error"


def embedding_error_code(code: str) -> str:
    return f"embedding_{code}"


class ClaimedJobDTO(BaseModel):
    model_config = {"frozen": True}

    product_id: int
    attempts: int


class StoredVectorDTO(BaseModel):
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
    model_config = {"frozen": True}

    product_id: int
    name: str
    category_name: str
    origin: str | None = None
    description: str

    stored_hash: str | None = None
    stored_vectors: dict[str, StoredVectorDTO] = Field(default_factory=dict)

    @property
    def is_indexed(self) -> bool:
        return self.stored_hash is not None

    def vector(self, slot: str) -> StoredVectorDTO:
        return self.stored_vectors.get(slot, StoredVectorDTO())


class SearchDocumentDTO(BaseModel):
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
    model: str
    dimensions: int
    vectors: dict[int, tuple[float, ...]] = field(default_factory=dict)


class VectorExpectationDTO(BaseModel):
    model_config = {"frozen": True}

    slot: str
    embedding_model: str
    embedding_dimensions: int


class IndexCoverageDTO(BaseModel):
    model_config = {"frozen": True}

    active_products: int
    documents: int
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
    model_config = {"frozen": True}

    product_id: int
    attempts: int
    last_error_code: str | None = None


class SweepReportDTO(BaseModel):
    model_config = {"frozen": True}

    pruned: int = 0
    enqueued: int = 0
    coverage: IndexCoverageDTO


class IndexRunReportDTO(BaseModel):
    model_config = {"frozen": True}

    claimed: int = 0
    indexed: int = 0
    failed: int = 0
    embedded: dict[str, int] = Field(default_factory=dict)
