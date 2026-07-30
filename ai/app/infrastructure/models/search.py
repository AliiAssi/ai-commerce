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

# The search schema. This service owns retrieval, so it owns these tables, and they carry the
# ai_ prefix that separates them from the store tables the web service owns in the same database.
#
# They hold real foreign keys to products. That coupling is not new — this service already reads
# the catalog at runtime through store_tables.py — so the choice is only whether the database
# enforces it or whether we hope for the best. Enforcing it means a deleted product cannot leave
# a stranded search document behind, and it costs one ordering rule: the web service's migrations
# run before this service's, which is already how the test and CI setups work.

# A foreign key needs its target resolvable in the same MetaData, and the real products table
# lives in store_metadata (store_tables.py) because this service only reads it. Declaring the
# primary key alone is enough for the constraints below to resolve. It is a reference to a table
# the web service owns and migrates, not a claim on it: migrations/env.py restricts autogenerate
# to ai_-prefixed tables, so alembic never proposes creating, altering, or dropping this one.
products = Table("products", Base.metadata, Column("id", Integer, primary_key=True))


def _hnsw(name: str, column: str) -> Index:
    """An HNSW index with cosine operators (§10.2).

    Cosine rather than L2 because the retrieval query ranks by `1 - (embedding <=> :q)`, and an
    index built for a different operator class simply would not be used — the query would fall
    back to a sequential scan and nothing would say so except a latency graph. `m` and
    `ef_construction` are pgvector's own defaults, named here so tuning them is a visible change
    rather than an inherited one.
    """
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
        # Lets the repair sweep find documents left behind by a document-format change.
        Index("ix_ai_search_documents_version", "document_version"),
        _hnsw("ix_ai_search_documents_embedding", "embedding"),
        _hnsw("ix_ai_search_documents_fallback_embedding", "fallback_embedding"),
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

    # Two embeddings per document, one per configured provider, because vectors from different
    # models are not comparable: a query embedded by the fallback and compared against a
    # primary-built column returns arbitrary neighbours rather than none, which §12 treats as
    # worse than falling back. Keeping both means each comparison has one model on both sides
    # and provider failover costs no re-embed.
    #
    # Nullable, and they must stay nullable: §10.2 forbids making the vector column NOT NULL
    # until the initial backfill has completed, and the fallback column stays NULL entirely when
    # no second provider is configured.
    #
    # The model and dimensions are stored beside each vector rather than assumed. They are what
    # lets the sweep notice that a document was embedded by a model the service is no longer
    # configured with — a state a document-hash comparison cannot see, because the text is
    # perfectly current.
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


class SearchQueryEmbedding(Base):
    """§10.4's bounded query-embedding cache — the reason a provider call is affordable.

    Query embedding measured a p50 of 434 ms against a 3 s deadline, and the free tier started
    refusing part-way through ninety sequential calls during the phase-5 bake-off. So this is
    not a latency optimisation on top of a working system; it is what makes sustained query
    traffic possible at all without Redis.

    The key is a SHA-256 over normalized semantic text, language, model, dimensions and the
    normalizer version — never the raw query, which §10.4 requires and §13 makes a privacy
    matter: a cache keyed on what a shopper typed is a log of what shoppers typed. Including the
    model and dimensions is what keeps two providers' vectors in separate rows instead of one
    silently serving the other's.
    """

    __tablename__ = "ai_search_query_embeddings"
    __table_args__ = (
        # The prune walks this, and only this. Everything else is a primary-key lookup.
        Index("ix_ai_search_query_embeddings_expires_at", "expires_at"),
    )

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)

    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSIONS), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding_dimensions: Mapped[int] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(8))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # An expiry column rather than a TTL applied at read time: a row that has expired must stop
    # being served *and* become collectable, and one timestamp does both.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
