from __future__ import annotations

from typing import Literal

# The vector width baked into the schema, and the one number that ties configuration to it.
#
# `vector(n)` fixes a dimension count in the migration. Changing it is not a settings change: it
# needs a new migration and a full re-embed of the catalog, because a stored vector of one width
# cannot be compared against a query vector of another. So the width lives here as a constant and
# `EMBEDDING_DIMENSIONS` is validated against it at boot (§10.2, §18.1 step 6) — a dashboard value
# drifting from the column would otherwise not fail until the first write, after a backfill had
# already been paid for.
#
# 768 rather than the model's native 3072 because pgvector will not build an HNSW index above
# 2000 dimensions, and because the phase-5 bake-off measured 768 as tying the best Arabic recall
# and MRR while halving both the column and the index on a 512 MB host. These models are
# Matryoshka-trained, so the truncation is a usable vector rather than a damaged one.
EMBEDDING_VECTOR_DIMENSIONS = 768

# Which of the two vector columns a query vector belongs to.
#
# Two columns rather than one because embeddings from different models occupy different spaces:
# a query embedded by the fallback provider and compared by cosine against primary-built vectors
# returns arbitrary neighbours, which is a confident wrong page rather than a degradation. Both
# sides of every comparison therefore come from the same model, and failover is a column choice
# rather than a re-embed.
EmbeddingSlot = Literal["primary", "fallback"]

PRIMARY_SLOT: EmbeddingSlot = "primary"
FALLBACK_SLOT: EmbeddingSlot = "fallback"
