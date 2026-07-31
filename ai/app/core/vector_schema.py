from __future__ import annotations

from typing import Literal

EMBEDDING_VECTOR_DIMENSIONS = 768

EmbeddingSlot = Literal["primary", "fallback"]

PRIMARY_SLOT: EmbeddingSlot = "primary"
FALLBACK_SLOT: EmbeddingSlot = "fallback"
