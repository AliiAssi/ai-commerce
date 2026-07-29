from __future__ import annotations

from datetime import datetime

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

from app.infrastructure.database.base import Base

# The search schema. This service owns retrieval, so it owns these tables, and they carry the
# ai_ prefix that separates them from the store tables the web service owns in the same database.
#
# They hold real foreign keys to products. That coupling is not new — this service already reads
# the catalog at runtime through store_tables.py — so the choice is only whether the database
# enforces it or whether we hope for the best. Enforcing it means a deleted product cannot leave
# a stranded search document behind, and it costs one ordering rule: the web service's migrations
# run before this service's, which is already how the test and CI setups work.
#
# The embedding columns are deliberately absent. A vector(n) column and its index bake in a
# dimension count that cannot be changed without re-embedding the whole catalog, so they wait
# until a model has actually been measured and chosen. Everything here is useful without them.

# A foreign key needs its target resolvable in the same MetaData, and the real products table
# lives in store_metadata (store_tables.py) because this service only reads it. Declaring the
# primary key alone is enough for the constraints below to resolve. It is a reference to a table
# the web service owns and migrates, not a claim on it: migrations/env.py restricts autogenerate
# to ai_-prefixed tables, so alembic never proposes creating, altering, or dropping this one.
products = Table("products", Base.metadata, Column("id", Integer, primary_key=True))


class SearchDocument(Base):
    __tablename__ = "ai_search_documents"
    __table_args__ = (
        Index("ix_ai_search_documents_en", "search_vector_en", postgresql_using="gin"),
        Index("ix_ai_search_documents_simple", "search_vector_simple", postgresql_using="gin"),
        # Lets the repair sweep find documents left behind by a document-format change.
        Index("ix_ai_search_documents_version", "document_version"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    document_text: Mapped[str] = mapped_column(Text)
    # Compared against a hash recomputed from live catalog data to detect drift, which is how
    # re-indexing is triggered without a shared transaction with the web service's writes.
    document_hash: Mapped[str] = mapped_column(String(64))
    document_version: Mapped[int] = mapped_column(Integer)

    # Two lexical representations, because one stemmer cannot serve both languages. English prose
    # stems well; 'simple' does no stemming, which is what Arabic, mixed text, and exact product
    # names need.
    search_vector_en: Mapped[str | None] = mapped_column(TSVECTOR)
    search_vector_simple: Mapped[str | None] = mapped_column(TSVECTOR)

    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchIndexJob(Base):
    __tablename__ = "ai_search_index_jobs"
    __table_args__ = (
        # The claim query orders by requested_at over rows that are due and unleased.
        Index("ix_ai_search_index_jobs_claim", "next_attempt_at", "requested_at"),
    )

    # product_id is the primary key rather than a surrogate id plus a unique constraint: the
    # queue holds at most one pending job per product, so a burst of edits coalesces into one
    # row via ON CONFLICT instead of piling up work the worker would only collapse later.
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
    # A crashed worker's lease simply expires; nothing needs to clean up after it.
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(64))
    # A code, never a provider message: these rows are read by operators and must not leak
    # credentials or provider internals.
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class SearchEvent(Base):
    __tablename__ = "ai_search_events"
    __table_args__ = (
        # Retention pruning walks this.
        Index("ix_ai_search_events_created_at", "created_at"),
        # "Top normalized queries" groups on the hash, never on the text.
        Index("ix_ai_search_events_query_hash", "normalized_query_hash"),
        # Zero-result queries are the highest-value report and a small slice of the table.
        Index(
            "ix_ai_search_events_zero_result",
            "created_at",
            postgresql_where=text("result_count = 0"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Redacted before it ever reaches this column, and dropped on a shorter clock than the
    # aggregate columns beside it. Nullable so metrics survive the text being pruned.
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

    # Version stamps: a ranking change that is not attributable to a version is not measurable.
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
