from __future__ import annotations

import hashlib

from app.application.search.normalizer import NORMALIZER_VERSION

CACHE_KEY_VERSION = "1"


def query_cache_key(
    *, semantic_text: str, language: str, embedding_model: str, dimensions: int
) -> str:
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
