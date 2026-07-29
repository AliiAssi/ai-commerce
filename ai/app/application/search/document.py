from __future__ import annotations

import hashlib

from app.application.dtos.index_dto import CatalogRowDTO, SearchDocumentDTO

# §7.1's document format version. Bump it whenever the text below changes shape, or whenever the
# setweight labels the worker stores change (search_index_repository.py) — both make every stored
# document wrong in a way no field edit would reveal, and the sweep's version comparison is what
# turns that into an automatic full rebuild.
DOCUMENT_VERSION = 1

# The fields §10.3 calls semantic. Everything else on a product — price, stock, rating, review
# count, image, archive state — is read live during filtering and ranking and must never enter
# the document, because a price change would otherwise re-embed the whole catalog (§7.1).
SEMANTIC_FIELDS = ("name", "category_name", "origin", "description")


def build_document_text(
    *, name: str, category_name: str, origin: str | None, description: str
) -> str:
    """§7.1's document, exactly.

    Field values go in raw — no strip(), no whitespace collapsing, no case folding. The drift
    sweep recomputes this same hash *in SQL* over the live catalog (§0.4), so the two
    implementations have to agree byte for byte, and Python's `str.strip()` and Postgres's
    `btrim()` do not strip the same set of characters. Raw concatenation is trivially equal in
    both languages; the cost is that a trailing space typed into the admin form triggers one
    harmless reindex, which is much the cheaper failure.

    The Origin line is omitted rather than left empty when there is no origin. `if origin` is
    false for both None and "", which is what `origin IS NULL OR origin = ''` means in the SQL
    twin. A whitespace-only origin is truthy in both.
    """
    lines = [f"Name: {name}", f"Category: {category_name}"]
    if origin:
        lines.append(f"Origin: {origin}")
    lines.append(f"Description: {description}")
    return "\n".join(lines)


def document_hash(document_text: str) -> str:
    """Lowercase hex SHA-256, matching `encode(sha256(convert_to(..., 'UTF8')), 'hex')`."""
    return hashlib.sha256(document_text.encode("utf-8")).hexdigest()


def build_document(row: CatalogRowDTO) -> SearchDocumentDTO:
    document_text = build_document_text(
        name=row.name,
        category_name=row.category_name,
        origin=row.origin,
        description=row.description,
    )
    return SearchDocumentDTO(
        product_id=row.product_id,
        name=row.name,
        category_name=row.category_name,
        origin=row.origin,
        description=row.description,
        document_text=document_text,
        document_hash=document_hash(document_text),
        document_version=DOCUMENT_VERSION,
    )
