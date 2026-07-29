from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import (
    ColumnElement,
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
    FailedJobDTO,
    IndexCoverageDTO,
    SearchDocumentDTO,
)
from app.application.search.document import DOCUMENT_VERSION
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.irepositories.isearch_index_repository import ISearchIndexRepository
from app.infrastructure.models.search import SearchDocument, SearchIndexJob

logger = logging.getLogger(__name__)

documents = SearchDocument.__table__
jobs = SearchIndexJob.__table__


def _document_text_sql() -> ColumnElement[str]:
    """The SQL twin of `build_document_text` in app/application/search/document.py.

    These two must produce the same bytes for the same product. The sweep compares a hash
    computed here against a hash computed there, so a one-character disagreement would mark
    every product permanently drifted and the worker would never idle — a failure that costs a
    provider call per product per sweep once phase 6 lands. `test_search_indexing.py` asserts
    equality across the whole seeded catalog rather than trusting the two to be read together.

    `if origin` in Python is false for None and for "", which is what this CASE says. Neither
    side trims: see the builder's docstring for why btrim() and str.strip() cannot be relied on
    to agree.
    """
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
    """`encode(sha256(convert_to(text, 'UTF8')), 'hex')` — built in since Postgres 11.

    No extension, and it returns only the drifted rows rather than the catalog (§0.4). The two
    encoding names are emitted literally so Postgres resolves them itself; `convert_to` takes a
    `name`, which a bound text parameter would not implicitly become.
    """
    return func.encode(
        func.sha256(func.convert_to(_document_text_sql(), literal_column("'UTF8'"))),
        literal_column("'hex'"),
    )


def _weighted_tsvector(config: str) -> ColumnElement[str]:
    """One lexical vector, weighted by which field each lexeme came from (§7.4).

    A = the product name, B = category and origin, D = the description. Without this, adding
    Category and Origin to the indexed text — which is the whole reason this table beats web's
    flat `products.search_vector` — would rank a category word as highly as a product name, and
    every product in "Olive Oil & Mouneh" would match `oil` as strongly as the olive oils do.

    These labels are stored *in* the tsvector, so changing the assignment needs a
    DOCUMENT_VERSION bump and a full rebuild. The numeric weights `ts_rank` multiplies them by
    are supplied per query from settings and can be retuned without touching a row.

    The labels are emitted literally rather than bound. `setweight`'s second argument is
    Postgres's single-byte `"char"`, and a parameter the driver types as varchar does not
    implicitly become one — the statement fails to resolve the function at all.
    """
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


# Claiming is one statement so the select and the lease cannot be separated by a crash. Rows
# another worker already holds are skipped rather than waited on, exhausted jobs are left alone
# for an operator, and a dead worker's lease simply expires (§11 rules 1 and 7).
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
    """The indexing pipeline's SQL. One session, supplied by whichever short scope opened it."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- enqueue ---------------------------------------------------------------------------

    def _drift_select(self):
        """§0.4's replacement for §10.3's transactional enqueue.

        Web writes products in its own transaction and this service cannot join it, so freshness
        comes from recomputing each active product's hash here and enqueuing only what disagrees.
        The version check catches a document-format change that no field edit would reveal.
        """
        return (
            select(products.c.id)
            .select_from(
                products.join(categories, categories.c.id == products.c.category_id).outerjoin(
                    documents, documents.c.product_id == products.c.id
                )
            )
            .where(
                products.c.is_archived.is_(False),
                or_(
                    documents.c.product_id.is_(None),
                    documents.c.document_version != DOCUMENT_VERSION,
                    documents.c.document_hash != _document_hash_sql(),
                ),
            )
        )

    async def drifted_product_ids(self) -> list[int]:
        rows = (await self._session.execute(self._drift_select())).scalars().all()
        return list(rows)

    async def enqueue_drifted(self) -> int:
        # DO NOTHING, deliberately not DO UPDATE. A job that already exists is already going to
        # be processed, and resetting attempts on every sweep would turn a permanently failing
        # product into an infinite retry loop that no attempt cap could ever stop. The CLI is
        # the path that resets, because there an operator is explicitly asking for a retry.
        stmt = (
            pg_insert(jobs)
            .from_select(["product_id"], self._drift_select())
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

    # ---- claim and finish ------------------------------------------------------------------

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
        # Archived products are excluded rather than reported missing. The correct index state
        # for an archived product is "no document", which the prune already produces, so the
        # caller finishes those jobs instead of burning attempts on a normal condition.
        stmt = (
            select(
                products.c.id,
                products.c.name,
                categories.c.name.label("category_name"),
                products.c.origin,
                products.c.description,
            )
            .select_from(products.join(categories, categories.c.id == products.c.category_id))
            .where(products.c.id.in_(product_ids), products.c.is_archived.is_(False))
        )
        return [
            CatalogRowDTO(
                product_id=row.id,
                name=row.name,
                category_name=row.category_name,
                origin=row.origin,
                description=row.description,
            )
            for row in (await self._session.execute(stmt)).all()
        ]

    async def write_documents(self, docs: Sequence[SearchDocumentDTO]) -> int:
        if not docs:
            return 0
        # Upsert, never delete-then-insert: §11 requires the last known-good document to survive
        # until its replacement is stored, which matters more once phase 6 makes the replacement
        # depend on a provider that can fail halfway through a batch.
        insert_stmt = pg_insert(documents).values(
            product_id=bindparam("product_id"),
            document_text=bindparam("document_text"),
            document_hash=bindparam("document_hash"),
            document_version=bindparam("document_version"),
            search_vector_en=_weighted_tsvector("english"),
            search_vector_simple=_weighted_tsvector("simple"),
            indexed_at=func.now(),
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["product_id"],
            set_={
                "document_text": insert_stmt.excluded.document_text,
                "document_hash": insert_stmt.excluded.document_hash,
                "document_version": insert_stmt.excluded.document_version,
                "search_vector_en": insert_stmt.excluded.search_vector_en,
                "search_vector_simple": insert_stmt.excluded.search_vector_simple,
                "indexed_at": insert_stmt.excluded.indexed_at,
            },
        )
        await self._session.execute(stmt, [_params(doc) for doc in docs])
        return len(docs)

    async def complete(self, product_ids: Sequence[int]) -> int:
        if not product_ids:
            return 0
        result = await self._session.execute(delete(jobs).where(jobs.c.product_id.in_(product_ids)))
        return result.rowcount or 0

    async def fail(self, product_id: int, *, error_code: str, delay_seconds: float) -> None:
        await self._session.execute(
            text(
                """
                UPDATE ai_search_index_jobs
                SET attempts = attempts + 1,
                    next_attempt_at = now() + (:delay * interval '1 second'),
                    last_error_code = :code,
                    lease_until = NULL,
                    worker_id = NULL
                WHERE product_id = :product_id
                """
            ),
            {"product_id": product_id, "code": error_code, "delay": delay_seconds},
        )

    async def release_leases(self, worker_id: str) -> int:
        result = await self._session.execute(
            jobs.update()
            .where(jobs.c.worker_id == worker_id)
            .values(lease_until=None, worker_id=None)
        )
        return result.rowcount or 0

    # ---- repair and reporting --------------------------------------------------------------

    async def prune_documents(self) -> int:
        """Documents whose product is archived or gone.

        The foreign key already cascades a *deleted* product's document away, so this exists for
        archival, which the constraint cannot see. Keeping the document set equal to the active
        product set is what lets coverage be a plain ratio rather than a number needing its own
        definition. The `NOT EXISTS` covers deletion too, at no extra cost, so a database
        restored from before the constraint existed repairs itself.
        """
        active = select(products.c.id).where(
            products.c.id == documents.c.product_id, products.c.is_archived.is_(False)
        )
        result = await self._session.execute(delete(documents).where(~active.exists()))
        return result.rowcount or 0

    async def coverage(self) -> IndexCoverageDTO:
        # One scan for both numbers. count(d.product_id) skips the null side of the outer join,
        # so a document belonging to an archived product is never counted as coverage.
        row = (
            await self._session.execute(
                select(func.count(), func.count(documents.c.product_id))
                .select_from(products.outerjoin(documents, documents.c.product_id == products.c.id))
                .where(products.c.is_archived.is_(False))
            )
        ).one()
        return IndexCoverageDTO(active_products=row[0], documents=row[1])

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


def _params(doc: SearchDocumentDTO) -> dict[str, object]:
    """Bind values for one document row.

    `facet_text` is assembled here rather than in the DTO because it exists only to be fed to
    `to_tsvector` for the B-weighted half of the vector. Coalescing the origin in Python also
    keeps a NULL of undetermined type out of the statement, which asyncpg will not infer.
    """
    return {
        "product_id": doc.product_id,
        "document_text": doc.document_text,
        "document_hash": doc.document_hash,
        "document_version": doc.document_version,
        "name": doc.name,
        "facet_text": f"{doc.category_name} {doc.origin or ''}",
        "description": doc.description,
    }
