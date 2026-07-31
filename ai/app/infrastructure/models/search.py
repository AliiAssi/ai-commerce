from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.vector_schema import EMBEDDING_VECTOR_DIMENSIONS
from app.infrastructure.database.base import Base

products = Table("products", Base.metadata, Column("id", Integer, primary_key=True))


def _hnsw(name: str, column: str) -> Index:
    return Index(
        name,
        column,
        postgresql_using="hnsw",
        postgresql_ops={column: "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )


class SearchDocument(Base):
    __tablename__ = "ai_search_documents"
    __table_args__ = (
        Index("ix_ai_search_documents_en", "search_vector_en", postgresql_using="gin"),
        Index("ix_ai_search_documents_simple", "search_vector_simple", postgresql_using="gin"),
        Index("ix_ai_search_documents_version", "document_version"),
        _hnsw("ix_ai_search_documents_embedding", "embedding"),
        _hnsw("ix_ai_search_documents_fallback_embedding", "fallback_embedding"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    document_text: Mapped[str] = mapped_column(Text)
    document_hash: Mapped[str] = mapped_column(String(64))
    document_version: Mapped[int] = mapped_column(Integer)

    search_vector_en: Mapped[str | None] = mapped_column(TSVECTOR)
    search_vector_simple: Mapped[str | None] = mapped_column(TSVECTOR)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_VECTOR_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)

    fallback_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSIONS)
    )
    fallback_embedding_model: Mapped[str | None] = mapped_column(String(100))
    fallback_embedding_dimensions: Mapped[int | None] = mapped_column(Integer)

    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchIndexJob(Base):
    __tablename__ = "ai_search_index_jobs"
    __table_args__ = (Index("ix_ai_search_index_jobs_claim", "next_attempt_at", "requested_at"),)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(64))
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class SearchQueryEmbedding(Base):
    __tablename__ = "ai_search_query_embeddings"
    __table_args__ = (Index("ix_ai_search_query_embeddings_expires_at", "expires_at"),)

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)

    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSIONS), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding_dimensions: Mapped[int] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(8))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchEvent(Base):
    __tablename__ = "ai_search_events"
    __table_args__ = (
        Index("ix_ai_search_events_created_at", "created_at"),
        Index("ix_ai_search_events_query_hash", "normalized_query_hash"),
        Index(
            "ix_ai_search_events_zero_result",
            "created_at",
            postgresql_where=text("result_count = 0"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    redacted_query: Mapped[str | None] = mapped_column(Text)
    normalized_query_hash: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(8))

    inferred_filters: Mapped[dict | None] = mapped_column(JSONB)
    explicit_filters: Mapped[dict | None] = mapped_column(JSONB)
    effective_sort: Mapped[str | None] = mapped_column(String(20))

    mode: Mapped[str | None] = mapped_column(String(24))
    reranked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    degraded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    degraded_reason: Mapped[str | None] = mapped_column(String(32))

    parser_version: Mapped[str | None] = mapped_column(String(20))
    ranker_version: Mapped[str | None] = mapped_column(String(20))
    reranker_version: Mapped[str | None] = mapped_column(String(20))
    embedding_model: Mapped[str | None] = mapped_column(String(100))

    rerank_candidate_count: Mapped[int | None] = mapped_column(Integer)
    rerank_outcome: Mapped[str | None] = mapped_column(String(24))

    result_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    page: Mapped[int | None] = mapped_column(Integer)
    page_size: Mapped[int | None] = mapped_column(Integer)

    total_latency_ms: Mapped[int | None] = mapped_column(Integer)
    embedding_latency_ms: Mapped[int | None] = mapped_column(Integer)
    reranker_latency_ms: Mapped[int | None] = mapped_column(Integer)
    query_cache_hit: Mapped[bool | None] = mapped_column(Boolean)
