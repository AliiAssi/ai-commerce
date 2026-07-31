from __future__ import annotations

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_DIMENSIONS = 768

_HNSW_WITH = {"m": 16, "ef_construction": 64}


def _add_vector_slot(prefix: str) -> None:
    op.add_column(
        "ai_search_documents",
        sa.Column(prefix, pgvector.sqlalchemy.Vector(_DIMENSIONS), nullable=True),
    )
    op.add_column(
        "ai_search_documents", sa.Column(f"{prefix}_model", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "ai_search_documents", sa.Column(f"{prefix}_dimensions", sa.Integer(), nullable=True)
    )


def _create_hnsw(name: str, column: str) -> None:
    op.create_index(
        name,
        "ai_search_documents",
        [column],
        postgresql_using="hnsw",
        postgresql_ops={column: "vector_cosine_ops"},
        postgresql_with=_HNSW_WITH,
    )


def upgrade() -> None:
    _add_vector_slot("embedding")
    _add_vector_slot("fallback_embedding")

    _create_hnsw("ix_ai_search_documents_embedding", "embedding")
    _create_hnsw("ix_ai_search_documents_fallback_embedding", "fallback_embedding")

    op.create_table(
        "ai_search_query_embeddings",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(_DIMENSIONS), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_key", name="pk_ai_search_query_embeddings"),
    )
    op.create_index(
        "ix_ai_search_query_embeddings_expires_at", "ai_search_query_embeddings", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_search_query_embeddings_expires_at", table_name="ai_search_query_embeddings"
    )
    op.drop_table("ai_search_query_embeddings")

    op.drop_index("ix_ai_search_documents_fallback_embedding", table_name="ai_search_documents")
    op.drop_index("ix_ai_search_documents_embedding", table_name="ai_search_documents")

    for prefix in ("fallback_embedding", "embedding"):
        op.drop_column("ai_search_documents", f"{prefix}_dimensions")
        op.drop_column("ai_search_documents", f"{prefix}_model")
        op.drop_column("ai_search_documents", prefix)
