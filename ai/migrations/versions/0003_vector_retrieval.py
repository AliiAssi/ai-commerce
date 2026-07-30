from __future__ import annotations

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

# vector retrieval: the embedding columns, their HNSW indexes, and the query-embedding cache
#
# 0002 deliberately left these out — `vector(n)` bakes in a dimension count that cannot be widened
# without re-embedding the catalog, so it waited for a model to be chosen by measurement (§18.1
# step 6). It has been: gemini-embedding-001 at 768 dimensions, which is also the widest pgvector
# will build an HNSW index over the model's native output for.
#
# Two vector columns rather than one. Embeddings from different models occupy different spaces, so
# a query embedded by the fallback provider and compared by cosine against primary-built vectors
# returns arbitrary neighbours — a confident wrong page, which §12 rates worse than falling back
# to lexical. One column per provider keeps the same model on both sides of every comparison.
#
# Every embedding column is nullable and stays that way. §10.2 forbids making the vector column
# NOT NULL before the initial backfill completes, and the fallback column remains entirely NULL
# when no second provider is configured.
#
# `CREATE EXTENSION vector` is not repeated here: 0002 already issues it, idempotently, and this
# migration cannot run without it having succeeded.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_DIMENSIONS = 768

# pgvector's own defaults, written out so retuning them is a visible change rather than an
# inherited one. §14.3 requires the search parameters to be tunable; these are the build-side
# pair, and `hnsw.ef_search` is the query-side one the repository sets per statement.
_HNSW_WITH = {"m": 16, "ef_construction": 64}


def _add_vector_slot(prefix: str) -> None:
    """One provider's vector plus the two columns that say what produced it.

    The model and dimensions are stored rather than assumed because they are the only way to
    notice a document embedded by a model the service is no longer configured with. Its text is
    perfectly current, so §0.4's hash-drift sweep cannot see it; these columns are what the sweep
    compares against configuration instead.
    """
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

    # Cosine operators, because retrieval ranks by `1 - (embedding <=> :q)`. An index built for a
    # different operator class is simply never used, and nothing reports that except latency.
    _create_hnsw("ix_ai_search_documents_embedding", "embedding")
    _create_hnsw("ix_ai_search_documents_fallback_embedding", "fallback_embedding")

    # §10.4. Keyed by a SHA-256 over normalized semantic text, language, model, dimensions and the
    # normalizer version — never the raw query, which is both what §10.4 requires and what keeps
    # this from becoming a log of what shoppers typed (§13).
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
    # The prune walks this and nothing else does; every read is a primary-key lookup.
    op.create_index(
        "ix_ai_search_query_embeddings_expires_at", "ai_search_query_embeddings", ["expires_at"]
    )

    # No HNSW index on the cache. Its only access path is an equality lookup on the key; a vector
    # index here would be built and maintained for a similarity search nothing performs.


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
