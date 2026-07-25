from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# where a good comes from — the provenance the storefront leads with
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("origin", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "origin")
