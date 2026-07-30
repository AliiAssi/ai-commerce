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

# The column prefix each slot owns. `embedding` keeps §10.2's name for the primary; the fallback
# mirrors it. Nothing outside this module needs to know either.
_SLOT_PREFIX = {PRIMARY_SLOT: "embedding", FALLBACK_SLOT: "fallback_embedding"}


def _slot_columns(slot: str):
    """The three columns one embedding slot owns: the vector, its model, and its width.

    A slot is named rather than passed as columns so callers deal in `"primary"`/`"fallback"` and
    only this module knows the column names. Unknown slots raise here rather than producing a
    query that quietly reads the wrong column.
    """
    prefix = _SLOT_PREFIX[slot]
    return (
        documents.c[prefix],
        documents.c[f"{prefix}_model"],
        documents.c[f"{prefix}_dimensions"],
    )


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

    def _drift_select(self, expectations: Sequence[VectorExpectationDTO] = ()):
        """§0.4's replacement for §10.3's transactional enqueue.

        Web writes products in its own transaction and this service cannot join it, so freshness
        comes from recomputing each active product's hash here and enqueuing only what disagrees.
        The version check catches a document-format change that no field edit would reveal.

        **The vector conditions are not an optimisation.** A document whose text is perfectly
        current but whose `embedding` is NULL — which is every document the moment migration 0003
        lands — is not drifted by any hash or version comparison, so without these it would never
        be enqueued and the semantic leg would never have anything to read. Production runs no
        build-step backfill; the in-process worker is the only thing that fills the index, so
        this has to live in the sweep rather than in the CLI.

        The re-enqueue loop this could become is already prevented by the caller: the sweep
        inserts with ON CONFLICT DO NOTHING, so a job that keeps failing keeps its attempts,
        stops being claimable at the cap, and stays in the table where the sweep cannot reset it.

        `expectations` is empty when no provider is configured, which reduces this to exactly the
        phase-4 predicate.
        """
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
        # DO NOTHING, deliberately not DO UPDATE. A job that already exists is already going to
        # be processed, and resetting attempts on every sweep would turn a permanently failing
        # product into an infinite retry loop that no attempt cap could ever stop. The CLI is
        # the path that resets, because there an operator is explicitly asking for a retry.
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
        #
        # The document's current state comes back in the same scan. The worker needs it to tell
        # which halves of a row are stale: a fallback provider being reconfigured must not make
        # the primary column re-embed, and a product with no document at all is the one case
        # that must still be written when a provider is down.
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
        """Upsert documents, and each slot's vector only where one was actually produced.

        Upsert, never delete-then-insert: §11 requires the last known-good document to survive
        until its replacement is stored, which matters more now that the replacement depends on a
        provider that can fail halfway through a batch.

        The vector columns are COALESCEd against their own previous values, so a slot with no new
        vector keeps whatever it had rather than being nulled. That is the same rule one level
        down: a provider outage must not destroy a working index.
        """
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
            # Typed explicitly: a bound None carries no type asyncpg can infer, and a vector
            # parameter it has to guess at fails outright rather than storing something wrong.
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
        """Record an attempt, back the job off, and release its lease.

        `attempts` overrides the increment, which is how §11 rule 6's "without retrying forever"
        is expressed: a permanent error jumps straight to the cap rather than spending five
        backoffs to reach the same answer. GREATEST keeps it monotonic, so a permanent failure
        can never *lower* a count an earlier retry already raised.

        The cast is not decoration: a bound NULL appearing only in `IS NULL` and `greatest()`
        gives Postgres nothing to infer a type from, and asyncpg refuses to prepare the statement
        at all rather than guessing.
        """
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

    async def coverage(self, expectations: Sequence[VectorExpectationDTO] = ()) -> IndexCoverageDTO:
        """Document coverage, plus one vector count per configured slot, in a single scan.

        One statement rather than one per readiness, so the two numbers describe the same instant.
        A document count and a vector count taken a moment apart could disagree in a way that
        would put the lexical leg on step 3 while the semantic leg believed a column it was
        reading was full.

        A vector only counts when its model and dimensions match what the service is configured
        with. Counting `embedding IS NOT NULL` instead would call a column full of another
        model's vectors ready, which is the one state that produces confident wrong results.
        """
        # count(d.product_id) skips the null side of the outer join, so a document belonging to
        # an archived product is never counted as coverage.
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
        """§10.4's pruning job. One indexed delete; the worker decides how often to call it."""
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
    """Bind values for one document row.

    `facet_text` is assembled here rather than in the DTO because it exists only to be fed to
    `to_tsvector` for the B-weighted half of the vector. Coalescing the origin in Python also
    keeps a NULL of undetermined type out of the statement, which asyncpg will not infer.

    A slot with no vector for this product binds three NULLs, which the statement's COALESCE
    turns into "leave whatever is stored alone".
    """
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
