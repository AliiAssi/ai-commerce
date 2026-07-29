from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_products_name_trgm",
        "products",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_origin_trgm",
        "products",
        ["origin"],
        postgresql_using="gin",
        postgresql_ops={"origin": "gin_trgm_ops"},
    )


def downgrade() -> None:
    # IF EXISTS, because dropping the extension takes these indexes with it (CASCADE) and
    # leaves the version table still pointing at 0004. Without the guard the downgrade then
    # fails on a missing index, and the migration is wedged: it cannot go down, and going up
    # is a no-op because alembic already believes it is applied. The extension itself is
    # deliberately not dropped — it may be shared with anything else in the database.
    op.execute("DROP INDEX IF EXISTS ix_products_origin_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_name_trgm")
