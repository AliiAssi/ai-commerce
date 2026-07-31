from __future__ import annotations

import hashlib

from app.application.dtos.index_dto import CatalogRowDTO, SearchDocumentDTO

DOCUMENT_VERSION = 1

SEMANTIC_FIELDS = ("name", "category_name", "origin", "description")


def build_document_text(
    *, name: str, category_name: str, origin: str | None, description: str
) -> str:
    lines = [f"Name: {name}", f"Category: {category_name}"]
    if origin:
        lines.append(f"Origin: {origin}")
    lines.append(f"Description: {description}")
    return "\n".join(lines)


def document_hash(document_text: str) -> str:
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
