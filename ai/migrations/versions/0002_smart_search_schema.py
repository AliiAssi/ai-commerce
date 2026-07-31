from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT to_regclass('public.products')")) is None:
        raise RuntimeError(
            "The 'products' table does not exist yet. Run the web service's migrations before "
            "this service's: the search tables reference the store catalog."
        )

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "ai_search_documents",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("document_text", sa.Text(), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("search_vector_en", postgresql.TSVECTOR(), nullable=True),
        sa.Column("search_vector_simple", postgresql.TSVECTOR(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_ai_search_documents_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", name="pk_ai_search_documents"),
    )
    op.create_index(
        "ix_ai_search_documents_en",
        "ai_search_documents",
        ["search_vector_en"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_ai_search_documents_simple",
        "ai_search_documents",
        ["search_vector_simple"],
        postgresql_using="gin",
    )
    op.create_index("ix_ai_search_documents_version", "ai_search_documents", ["document_version"])

    op.create_table(
        "ai_search_index_jobs",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_ai_search_index_jobs_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", name="pk_ai_search_index_jobs"),
    )
    op.create_index(
        "ix_ai_search_index_jobs_claim",
        "ai_search_index_jobs",
        ["next_attempt_at", "requested_at"],
    )

    op.create_table(
        "ai_search_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("redacted_query", sa.Text(), nullable=True),
        sa.Column("normalized_query_hash", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("inferred_filters", postgresql.JSONB(), nullable=True),
        sa.Column("explicit_filters", postgresql.JSONB(), nullable=True),
        sa.Column("effective_sort", sa.String(length=20), nullable=True),
        sa.Column("mode", sa.String(length=24), nullable=True),
        sa.Column("reranked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("degraded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("degraded_reason", sa.String(length=32), nullable=True),
        sa.Column("parser_version", sa.String(length=20), nullable=True),
        sa.Column("ranker_version", sa.String(length=20), nullable=True),
        sa.Column("reranker_version", sa.String(length=20), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("rerank_candidate_count", sa.Integer(), nullable=True),
        sa.Column("rerank_outcome", sa.String(length=24), nullable=True),
        sa.Column("result_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("page_size", sa.Integer(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("embedding_latency_ms", sa.Integer(), nullable=True),
        sa.Column("reranker_latency_ms", sa.Integer(), nullable=True),
        sa.Column("query_cache_hit", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ai_search_events"),
    )
    op.create_index("ix_ai_search_events_created_at", "ai_search_events", ["created_at"])
    op.create_index("ix_ai_search_events_query_hash", "ai_search_events", ["normalized_query_hash"])
    op.create_index(
        "ix_ai_search_events_zero_result",
        "ai_search_events",
        ["created_at"],
        postgresql_where=sa.text("result_count = 0"),
    )


def downgrade() -> None:
    op.drop_index("ix_ai_search_events_zero_result", table_name="ai_search_events")
    op.drop_index("ix_ai_search_events_query_hash", table_name="ai_search_events")
    op.drop_index("ix_ai_search_events_created_at", table_name="ai_search_events")
    op.drop_table("ai_search_events")

    op.drop_index("ix_ai_search_index_jobs_claim", table_name="ai_search_index_jobs")
    op.drop_table("ai_search_index_jobs")

    op.drop_index("ix_ai_search_documents_version", table_name="ai_search_documents")
    op.drop_index("ix_ai_search_documents_simple", table_name="ai_search_documents")
    op.drop_index("ix_ai_search_documents_en", table_name="ai_search_documents")
    op.drop_table("ai_search_documents")
