from __future__ import annotations

import hashlib

from app.application.search.normalizer import NORMALIZER_VERSION

# The cache key's own version, separate from the normalizer's.
#
# The normalizer version covers *what the text became*; this covers *what the key is made of*.
# Adding or reordering a component changes every key without changing any input, and an old row
# served under a new scheme would be a vector for a query nobody asked. Bumping this invalidates
# the whole cache, which for a table with a 24-hour TTL costs one day of provider calls.
CACHE_KEY_VERSION = "1"


def query_cache_key(
    *, semantic_text: str, language: str, embedding_model: str, dimensions: int
) -> str:
    """§10.4's cache key: SHA-256 over the normalized text and everything that changes its meaning.

    Explicitly **not** the raw query. §10.4 forbids it and §13 explains why: a cache keyed on what
    a shopper typed is a durable log of what shoppers typed, sitting outside the retention rules
    the analytics table has. A hash is enough to find a row and useless for reading one.

    The model and dimensions are in the key because a vector is only meaningful against the index
    built by the same model — which is also why they are stored on the row and checked on read.
    The normalizer version is in the key because a change to folding or digit handling makes the
    same input produce different text, and a cached vector for the old text would be silently
    wrong rather than merely stale.
    """
    material = "\x1f".join(
        (
            CACHE_KEY_VERSION,
            NORMALIZER_VERSION,
            language,
            embedding_model,
            str(dimensions),
            semantic_text,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
