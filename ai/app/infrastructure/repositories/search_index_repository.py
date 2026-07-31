from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ColumnElement,
    Integer,
    String,
    bindparam,
    case,
    delete,
    func,
    literal,
    literal_column,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.index_dto import (
    CatalogRowDTO,
    ClaimedJobDTO,
    EmbeddedSlot,
    FailedJobDTO,
    IndexCoverageDTO,
    SearchDocumentDTO,
    StoredVectorDTO,
    VectorExpectationDTO,
)
from app.application.search.document import DOCUMENT_VERSION
from app.core.vector_schema import (
    EMBEDDING_VECTOR_DIMENSIONS,
    FALLBACK_SLOT,
    PRIMARY_SLOT,
)
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.irepositories.isearch_index_repository import ISearchIndexRepository
from app.infrastructure.models.search import (
    SearchDocument,
    SearchIndexJob,
    SearchQueryEmbedding,
)

logger = logging.getLogger(__name__)

documents = SearchDocument.__table__
jobs = SearchIndexJob.__table__
query_embeddings = SearchQueryEmbedding.__table__

_SLOT_PREFIX = {PRIMARY_SLOT: "embedding", FALLBACK_SLOT: "fallback_embedding"}


def _slot_columns(slot: str):
    prefix = _SLOT_PREFIX[slot]
    return (
        documents.c[prefix],
        documents.c[f"{prefix}_model"],
        documents.c[f"{prefix}_dimensions"],
    )


def _document_text_sql() -> ColumnElement[str]:
    origin_line = case(
        (or_(products.c.origin.is_(None), products.c.origin == ""), literal("", String)),
        else_=literal("\nOrigin: ", String) + products.c.origin,
    )
    return (
        literal("Name: ", String)
        + products.c.name
        + literal("\nCategory: ", String)
        + categories.c.name
        + origin_line
        + literal("\nDescription: ", String)
        + products.c.description
    )


def _document_hash_sql() -> ColumnElement[str]:
    return func.encode(
        func.sha256(func.convert_to(_document_text_sql(), literal_column("'UTF8'"))),
        literal_column("'hex'"),
    )


def _weighted_tsvector(config: str) -> ColumnElement[str]:
    return (
        func.setweight(func.to_tsvector(config, bindparam("name")), literal_column("'A'"))
        .op("||")(
            func.setweight(func.to_tsvector(config, bindparam("facet_text")), literal_column("'B'"))
        )
        .op("||")(
            func.setweight(
                func.to_tsvector(config, bindparam("description")), literal_column("'D'")
            )
        )
    )


_CLAIM_SQL = text(
    """
    WITH due AS (
        SELECT product_id
        FROM ai_search_index_jobs
        WHERE next_attempt_at <= now()
          AND attempts < :max_attempts
          AND (lease_until IS NULL OR lease_until < now())
        ORDER BY requested_at, product_id
        LIMIT :size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE ai_search_index_jobs AS j
    SET lease_until = now() + (:lease_seconds * interval '1 second'),
        worker_id = :worker_id
    FROM due
    WHERE j.product_id = due.product_id
    RETURNING j.product_id, j.attempts
    """
)


class SearchIndexRepository(ISearchIndexRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _drift_select(self, expectations: Sequence[VectorExpectationDTO] = ()):
        drifted = [
            documents.c.product_id.is_(None),
            documents.c.document_version != DOCUMENT_VERSION,
            documents.c.document_hash != _document_hash_sql(),
        ]
        for expectation in expectations:
            vector, model, dimensions = _slot_columns(expectation.slot)
            drifted.append(
                or_(
                    vector.is_(None),
                    model.is_distinct_from(expectation.embedding_model),
                    dimensions.is_distinct_from(expectation.embedding_dimensions),
                )
            )
        return (
            select(products.c.id)
            .select_from(
                products.join(categories, categories.c.id == products.c.category_id).outerjoin(
                    documents, documents.c.product_id == products.c.id
                )
            )
            .where(products.c.is_archived.is_(False), or_(*drifted))
        )

    async def drifted_product_ids(
        self, expectations: Sequence[VectorExpectationDTO] = ()
    ) -> list[int]:
        rows = (await self._session.execute(self._drift_select(expectations))).scalars().all()
        return list(rows)

    async def enqueue_drifted(self, expectations: Sequence[VectorExpectationDTO] = ()) -> int:
        stmt = (
            pg_insert(jobs)
            .from_select(["product_id"], self._drift_select(expectations))
            .on_conflict_do_nothing(index_elements=["product_id"])
            .returning(jobs.c.product_id)
        )
        return len((await self._session.execute(stmt)).scalars().all())

    async def enqueue_products(self, product_ids: Sequence[int], *, reset: bool) -> int:
        if not product_ids:
            return 0
        stmt = pg_insert(jobs).values([{"product_id": pid} for pid in product_ids])
        if reset:
            stmt = stmt.on_conflict_do_update(
                index_elements=["product_id"],
                set_={
                    "requested_at": func.now(),
                    "attempts": 0,
                    "next_attempt_at": func.now(),
                    "last_error_code": None,
                    "lease_until": None,
                    "worker_id": None,
                },
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["product_id"])
        result = await self._session.execute(stmt.returning(jobs.c.product_id))
        return len(result.scalars().all())

    async def active_product_ids(self) -> list[int]:
        rows = (
            (
                await self._session.execute(
                    select(products.c.id).where(products.c.is_archived.is_(False))
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def claim_batch(
        self, *, worker_id: str, size: int, lease_seconds: int, max_attempts: int
    ) -> list[ClaimedJobDTO]:
        rows = await self._session.execute(
            _CLAIM_SQL,
            {
                "worker_id": worker_id,
                "size": size,
                "lease_seconds": lease_seconds,
                "max_attempts": max_attempts,
            },
        )
        return [
            ClaimedJobDTO(product_id=row.product_id, attempts=row.attempts) for row in rows.all()
        ]

    async def load_rows(self, product_ids: Sequence[int]) -> list[CatalogRowDTO]:
        if not product_ids:
            return []
        columns = [
            products.c.id,
            products.c.name,
            categories.c.name.label("category_name"),
            products.c.origin,
            products.c.description,
            documents.c.document_hash.label("stored_hash"),
        ]
        for slot in _SLOT_PREFIX:
            vector, model, dimensions = _slot_columns(slot)
            columns += [
                vector.is_not(None).label(f"{slot}_present"),
                model.label(f"{slot}_model"),
                dimensions.label(f"{slot}_dimensions"),
            ]

        stmt = (
            select(*columns)
            .select_from(
                products.join(categories, categories.c.id == products.c.category_id).outerjoin(
                    documents, documents.c.product_id == products.c.id
                )
            )
            .where(products.c.id.in_(product_ids), products.c.is_archived.is_(False))
        )
        return [
            CatalogRowDTO(
                product_id=row.id,
                name=row.name,
                category_name=row.category_name,
                origin=row.origin,
                description=row.description,
                stored_hash=row.stored_hash,
                stored_vectors={
                    slot: StoredVectorDTO(
                        present=bool(getattr(row, f"{slot}_present")),
                        embedding_model=getattr(row, f"{slot}_model"),
                        embedding_dimensions=getattr(row, f"{slot}_dimensions"),
                    )
                    for slot in _SLOT_PREFIX
                },
            )
            for row in (await self._session.execute(stmt)).all()
        ]

    async def write_documents(
        self,
        docs: Sequence[SearchDocumentDTO],
        vectors: Mapping[str, EmbeddedSlot] | None = None,
    ) -> int:
        if not docs:
            return 0
        vectors = vectors or {}

        values = {
            "product_id": bindparam("product_id"),
            "document_text": bindparam("document_text"),
            "document_hash": bindparam("document_hash"),
            "document_version": bindparam("document_version"),
            "search_vector_en": _weighted_tsvector("english"),
            "search_vector_simple": _weighted_tsvector("simple"),
            "indexed_at": func.now(),
        }
        for prefix in _SLOT_PREFIX.values():
            values[prefix] = bindparam(prefix, type_=Vector(EMBEDDING_VECTOR_DIMENSIONS))
            values[f"{prefix}_model"] = bindparam(f"{prefix}_model", type_=String)
            values[f"{prefix}_dimensions"] = bindparam(f"{prefix}_dimensions", type_=Integer)

        insert_stmt = pg_insert(documents).values(**values)
        updates = {
            "document_text": insert_stmt.excluded.document_text,
            "document_hash": insert_stmt.excluded.document_hash,
            "document_version": insert_stmt.excluded.document_version,
            "search_vector_en": insert_stmt.excluded.search_vector_en,
            "search_vector_simple": insert_stmt.excluded.search_vector_simple,
            "indexed_at": insert_stmt.excluded.indexed_at,
        }
        for prefix in _SLOT_PREFIX.values():
            for column in (prefix, f"{prefix}_model", f"{prefix}_dimensions"):
                updates[column] = func.coalesce(insert_stmt.excluded[column], documents.c[column])

        stmt = insert_stmt.on_conflict_do_update(index_elements=["product_id"], set_=updates)
        await self._session.execute(stmt, [_params(doc, vectors) for doc in docs])
        return len(docs)

    async def complete(self, product_ids: Sequence[int]) -> int:
        if not product_ids:
            return 0
        result = await self._session.execute(delete(jobs).where(jobs.c.product_id.in_(product_ids)))
        return result.rowcount or 0

    async def fail(
        self,
        product_id: int,
        *,
        error_code: str,
        delay_seconds: float,
        attempts: int | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE ai_search_index_jobs
                SET attempts = CASE
                        WHEN CAST(:attempts AS integer) IS NULL THEN attempts + 1
                        ELSE greatest(attempts + 1, CAST(:attempts AS integer))
                    END,
                    next_attempt_at = now() + (:delay * interval '1 second'),
                    last_error_code = :code,
                    lease_until = NULL,
                    worker_id = NULL
                WHERE product_id = :product_id
                """
            ),
            {
                "product_id": product_id,
                "code": error_code,
                "delay": delay_seconds,
                "attempts": attempts,
            },
        )

    async def release_leases(self, worker_id: str) -> int:
        result = await self._session.execute(
            jobs.update()
            .where(jobs.c.worker_id == worker_id)
            .values(lease_until=None, worker_id=None)
        )
        return result.rowcount or 0

    async def prune_documents(self) -> int:
        active = select(products.c.id).where(
            products.c.id == documents.c.product_id, products.c.is_archived.is_(False)
        )
        result = await self._session.execute(delete(documents).where(~active.exists()))
        return result.rowcount or 0

    async def coverage(self, expectations: Sequence[VectorExpectationDTO] = ()) -> IndexCoverageDTO:
        columns = [func.count(), func.count(documents.c.product_id)]
        for expectation in expectations:
            vector, model, dimensions = _slot_columns(expectation.slot)
            columns.append(
                func.count(
                    case(
                        (
                            vector.is_not(None)
                            & (model == expectation.embedding_model)
                            & (dimensions == expectation.embedding_dimensions),
                            documents.c.product_id,
                        )
                    )
                )
            )

        row = (
            await self._session.execute(
                select(*columns)
                .select_from(products.outerjoin(documents, documents.c.product_id == products.c.id))
                .where(products.c.is_archived.is_(False))
            )
        ).one()
        return IndexCoverageDTO(
            active_products=row[0],
            documents=row[1],
            embedded={
                expectation.slot: row[index]
                for index, expectation in enumerate(expectations, start=2)
            },
        )

    async def prune_query_cache(self) -> int:
        result = await self._session.execute(
            delete(query_embeddings).where(query_embeddings.c.expires_at <= func.now())
        )
        return result.rowcount or 0

    async def pending_count(self) -> int:
        return await self._session.scalar(select(func.count()).select_from(jobs)) or 0

    async def failed_jobs(self, max_attempts: int) -> list[FailedJobDTO]:
        rows = (
            await self._session.execute(
                select(jobs.c.product_id, jobs.c.attempts, jobs.c.last_error_code)
                .where(jobs.c.attempts >= max_attempts)
                .order_by(jobs.c.product_id)
            )
        ).all()
        return [
            FailedJobDTO(
                product_id=row.product_id,
                attempts=row.attempts,
                last_error_code=row.last_error_code,
            )
            for row in rows
        ]


def _params(doc: SearchDocumentDTO, vectors: Mapping[str, EmbeddedSlot]) -> dict[str, object]:
    params: dict[str, object] = {
        "product_id": doc.product_id,
        "document_text": doc.document_text,
        "document_hash": doc.document_hash,
        "document_version": doc.document_version,
        "name": doc.name,
        "facet_text": f"{doc.category_name} {doc.origin or ''}",
        "description": doc.description,
    }
    for slot, prefix in _SLOT_PREFIX.items():
        embedded = vectors.get(slot)
        vector = embedded.vectors.get(doc.product_id) if embedded else None
        params[prefix] = list(vector) if vector is not None else None
        params[f"{prefix}_model"] = embedded.model if vector is not None else None
        params[f"{prefix}_dimensions"] = embedded.dimensions if vector is not None else None
    return params
