from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    REAL,
    ColumnElement,
    Integer,
    Select,
    String,
    bindparam,
    case,
    func,
    literal,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.search_dto import (
    CatalogLexiconDTO,
    EffectiveFilters,
    QueryVectorDTO,
    RetrievalRequest,
    RetrievalResult,
)
from app.application.rerank.ireranker import RerankCandidate
from app.application.search.normalizer import fold_for_matching, tokenize
from app.core.config import Settings
from app.core.index_state import IndexCoverage
from app.core.vector_schema import FALLBACK_SLOT, PRIMARY_SLOT
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.models.search import SearchDocument, SearchQueryEmbedding

logger = logging.getLogger(__name__)

RANKER_VERSION = "3"

documents = SearchDocument.__table__
query_embeddings = SearchQueryEmbedding.__table__

_SLOT_COLUMN = {
    PRIMARY_SLOT: documents.c.embedding,
    FALLBACK_SLOT: documents.c.fallback_embedding,
}

TRIGRAM_EXTENSION = "pg_trgm"


_MIN_TRIGRAM_TOKEN = 4
_MAX_TRIGRAM_TOKENS = 8

_TSQUERY_UNSAFE = re.compile(r"[^\w]", re.UNICODE)

_SORTS = {
    "newest": (products.c.created_at.desc(), products.c.id.desc()),
    "price_asc": (products.c.price.asc(), products.c.id.asc()),
    "price_desc": (products.c.price.desc(), products.c.id.asc()),
    "rating": (products.c.rating_avg.desc(), products.c.review_count.desc(), products.c.id.asc()),
}


def trigram_tokens(semantic_text: str) -> list[str]:
    folded = fold_for_matching(semantic_text)
    tokens = [token for token in tokenize(folded) if len(token) >= _MIN_TRIGRAM_TOKEN]
    return list(dict.fromkeys(tokens))[:_MAX_TRIGRAM_TOKENS]


def lexical_tokens(semantic_text: str) -> list[str]:
    tokens = [_TSQUERY_UNSAFE.sub("", token) for token in tokenize(semantic_text)]
    return list(dict.fromkeys(token for token in tokens if token))


def _tied_rank(ranked):
    return func.rank().over(order_by=ranked.c.score.desc())


def _empty(request: RetrievalRequest, *, semantic_used: bool = False) -> RetrievalResult:
    return RetrievalResult(
        product_ids=[],
        total=0,
        page=request.page,
        page_size=request.page_size,
        semantic_used=semantic_used,
    )


def filtered_products(filters: EffectiveFilters) -> Select:
    stmt = (
        select(products.c.id)
        .select_from(products.join(categories, categories.c.id == products.c.category_id))
        .where(products.c.is_archived.is_(False))
    )
    if filters.category_slug:
        stmt = stmt.where(categories.c.slug == filters.category_slug)
    if filters.origins:
        stmt = stmt.where(products.c.origin.in_(filters.origins))
    if filters.min_price is not None:
        stmt = stmt.where(products.c.price >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(products.c.price <= filters.max_price)
    if filters.in_stock_only:
        stmt = stmt.where(products.c.stock > 0)
    return stmt


@dataclass(slots=True)
class SearchCapabilities:
    trigram: bool = True


class SearchRepository(ISearchRepository):
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        capabilities: SearchCapabilities,
        coverage: IndexCoverage,
    ) -> None:
        self._session = session
        self._settings = settings
        self._capabilities = capabilities
        self._coverage = coverage

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        if not request.semantic_text.strip():
            return await self._browse(request)
        return await self._fused(request)

    async def _browse(
        self, request: RetrievalRequest, *, semantic_used: bool = False
    ) -> RetrievalResult:
        stmt = filtered_products(request.filters)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery("filtered_count"))
        )
        order = _SORTS.get(request.filters.sort) or _SORTS["newest"]
        rows = (
            await self._session.execute(
                stmt.order_by(*order)
                .limit(request.page_size)
                .offset((request.page - 1) * request.page_size)
            )
        ).all()
        return RetrievalResult(
            product_ids=[row.id for row in rows],
            total=total or 0,
            page=request.page,
            page_size=request.page_size,
            filters_only=True,
            semantic_used=semantic_used,
        )

    async def _fused(self, request: RetrievalRequest) -> RetrievalResult:
        settings = self._settings
        filters = request.filters
        filtered = filtered_products(filters).cte("filtered")

        use_documents = self._coverage.ready
        lex = self._lexical_cte(filtered, request.semantic_text, use_documents=use_documents)
        sem = await self._semantic_cte(filtered, request.query_vector)
        semantic_used = sem is not None
        if lex is None and sem is None:
            return (
                await self._browse(request, semantic_used=semantic_used)
                if filters.has_filters
                else _empty(request, semantic_used=semantic_used)
            )

        tokens = trigram_tokens(request.semantic_text) if self._capabilities.trigram else []
        trg = self._trigram_cte(filtered, tokens, filters) if tokens else None

        legs = {"sem": sem, "lex": lex, "trg": trg}
        eligible = self._fuse(legs).cte("fused")
        eligible = (
            select(*eligible.c)
            .where(eligible.c.score >= settings.SEARCH_RELEVANCE_FLOOR)
            .cte("eligible")
        )

        counts = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count(eligible.c.sem_rank),
                    func.count(eligible.c.lex_rank),
                    func.count(eligible.c.trg_rank),
                ).select_from(eligible)
            )
        ).one()
        total, semantic_hits, lexical_hits, trigram_hits = counts
        if not total:
            return (
                await self._browse(request, semantic_used=semantic_used)
                if filters.has_filters
                else _empty(request, semantic_used=semantic_used)
            )

        page = (
            select(products.c.id)
            .select_from(
                products.join(eligible, eligible.c.id == products.c.id).join(
                    categories, categories.c.id == products.c.category_id
                )
            )
            .order_by(*self._ordering(request, eligible))
            .limit(request.page_size)
            .offset((request.page - 1) * request.page_size)
        )
        rows = (await self._session.execute(page)).all()

        return RetrievalResult(
            product_ids=[row.id for row in rows],
            total=total,
            page=request.page,
            page_size=request.page_size,
            semantic_hits=semantic_hits,
            lexical_hits=lexical_hits,
            trigram_hits=trigram_hits,
            semantic_used=semantic_used,
            documents_used=use_documents,
        )

    def _fuse(self, legs: dict[str, object]) -> Select:
        present = [(name, leg) for name, leg in legs.items() if leg is not None]
        joined = present[0][1]
        ids = [present[0][1].c.id]
        for _, leg in present[1:]:
            key = ids[0] if len(ids) == 1 else func.coalesce(*ids)
            joined = joined.join(leg, key == leg.c.id, full=True)
            ids.append(leg.c.id)

        null_rank = literal(None, type_=Integer)
        columns = [
            (func.coalesce(*ids) if len(ids) > 1 else ids[0]).label("id"),
            self._rrf_score(present).label("score"),
        ]
        for name in legs:
            leg = legs[name]
            columns.append((leg.c.rank if leg is not None else null_rank).label(f"{name}_rank"))
        return select(*columns).select_from(joined)

    async def _semantic_cte(self, filtered, query_vector: QueryVectorDTO | None):
        if query_vector is None or not self._coverage.semantic(query_vector.slot):
            return None
        column = _SLOT_COLUMN.get(query_vector.slot)
        if column is None:
            return None

        await self._session.execute(
            text(
                "SELECT set_config('hnsw.ef_search', :ef_search, true), "
                "set_config('hnsw.iterative_scan', :iterative_scan, true)"
            ),
            {
                "ef_search": str(self._settings.SEARCH_HNSW_EF_SEARCH),
                "iterative_scan": self._settings.SEARCH_HNSW_ITERATIVE_SCAN,
            },
        )

        vector = bindparam("query_vector", value=list(query_vector.values), type_=Vector)
        distance = column.cosine_distance(vector)
        similarity = literal(1.0) - distance
        ranked = (
            select(documents.c.product_id.label("id"), similarity.label("score"))
            .select_from(documents.join(filtered, filtered.c.id == documents.c.product_id))
            .where(
                column.is_not(None),
                similarity >= self._settings.SEARCH_SEMANTIC_MIN_SIMILARITY,
            )
            .order_by(distance.asc(), documents.c.product_id.asc())
            .limit(self._settings.SEARCH_SEMANTIC_CANDIDATES)
            .subquery("semantic_ranked")
        )
        return select(ranked.c.id, _tied_rank(ranked).label("rank")).cte("sem")

    def _lexical_cte(self, filtered, semantic_text: str, *, use_documents: bool):
        tokens = lexical_tokens(semantic_text)
        if not tokens:
            return None
        if use_documents:
            return self._document_lexical_cte(filtered, tokens)
        return self._catalog_lexical_cte(filtered, " | ".join(tokens))

    def _document_lexical_cte(self, filtered, tokens: list[str]):
        query_en = func.to_tsquery("english", " | ".join(tokens))
        query_simple = func.to_tsquery("simple", self._content_tokens(tokens))
        weights = self._rank_weights()
        rank = func.greatest(
            func.ts_rank(weights, documents.c.search_vector_en, query_en),
            func.ts_rank(weights, documents.c.search_vector_simple, query_simple),
        )
        ranked = (
            select(documents.c.product_id.label("id"), rank.label("score"))
            .select_from(documents.join(filtered, filtered.c.id == documents.c.product_id))
            .where(
                or_(
                    documents.c.search_vector_en.op("@@")(query_en),
                    documents.c.search_vector_simple.op("@@")(query_simple),
                )
            )
            .order_by(rank.desc(), documents.c.product_id.asc())
            .limit(self._settings.SEARCH_LEXICAL_CANDIDATES)
            .subquery("lexical_ranked")
        )
        return select(ranked.c.id, _tied_rank(ranked).label("rank")).cte("lex")

    def _catalog_lexical_cte(self, filtered, expression: str):
        tsquery = func.to_tsquery("english", expression)
        rank = func.ts_rank(products.c.search_vector, tsquery)
        ranked = (
            select(products.c.id.label("id"), rank.label("score"))
            .select_from(products.join(filtered, filtered.c.id == products.c.id))
            .where(products.c.search_vector.op("@@")(tsquery))
            .order_by(rank.desc(), products.c.id.asc())
            .limit(self._settings.SEARCH_LEXICAL_CANDIDATES)
            .subquery("lexical_ranked")
        )
        return select(ranked.c.id, _tied_rank(ranked).label("rank")).cte("lex")

    def _content_tokens(self, tokens: list[str]):
        token = func.unnest(
            bindparam("lexical_tokens", value=tokens, type_=ARRAY(String))
        ).column_valued("lexical_token")
        return (
            select(func.string_agg(token, literal(" | ")))
            .where(func.length(func.to_tsvector("english", token)) > 0)
            .scalar_subquery()
        )

    def _rank_weights(self):
        settings = self._settings
        return bindparam(
            "ts_weights",
            value=[
                settings.SEARCH_LEXICAL_WEIGHT_DESCRIPTION,
                settings.SEARCH_LEXICAL_WEIGHT_DESCRIPTION,
                settings.SEARCH_LEXICAL_WEIGHT_FACET,
                settings.SEARCH_LEXICAL_WEIGHT_NAME,
            ],
            type_=ARRAY(REAL),
        )

    def _trigram_cte(self, filtered, tokens: list[str], filters: EffectiveFilters):
        token = func.unnest(
            bindparam("trigram_tokens", value=tokens, type_=ARRAY(String))
        ).column_valued("candidate_token")

        targets = [func.word_similarity(token, products.c.name)]
        if not filters.origins:
            targets.append(func.word_similarity(token, func.coalesce(products.c.origin, "")))

        best = targets[0] if len(targets) == 1 else func.greatest(*targets)
        similarity = select(func.max(best)).scalar_subquery()
        scored = (
            select(products.c.id.label("id"), similarity.label("score"))
            .select_from(products.join(filtered, filtered.c.id == products.c.id))
            .subquery("trigram_scored")
        )
        ranked = (
            select(scored.c.id, scored.c.score)
            .where(scored.c.score >= self._settings.SEARCH_TRIGRAM_THRESHOLD)
            .order_by(scored.c.score.desc(), scored.c.id.asc())
            .limit(self._settings.SEARCH_TRIGRAM_CANDIDATES)
            .subquery("trigram_ranked")
        )
        return select(ranked.c.id, _tied_rank(ranked).label("rank")).cte("trg")

    def _rrf_score(self, present) -> ColumnElement[float]:
        k = self._settings.SEARCH_RRF_K
        weights = {
            "sem": self._settings.SEARCH_RRF_WEIGHT_SEMANTIC,
            "lex": self._settings.SEARCH_RRF_WEIGHT_LEXICAL,
            "trg": self._settings.SEARCH_RRF_WEIGHT_TRIGRAM,
        }
        total: ColumnElement[float] | None = None
        for name, leg in present:
            term = func.coalesce(literal(weights[name]) / (k + leg.c.rank), 0.0)
            total = term if total is None else total + term
        assert total is not None
        return total

    def _ordering(self, request: RetrievalRequest, eligible):
        exact_name = case(
            (func.lower(func.trim(products.c.name)) == request.normalized_query, 1), else_=0
        ).desc()

        if request.filters.sort != "relevance":
            return (exact_name, *_SORTS[request.filters.sort])

        phrase_match = case(
            (func.lower(categories.c.name) == request.normalized_query, 1),
            (func.lower(func.coalesce(products.c.origin, "")) == request.normalized_query, 1),
            else_=0,
        ).desc()
        in_stock = case((products.c.stock > 0, 1), else_=0).desc()
        return (
            exact_name,
            eligible.c.score.desc(),
            phrase_match,
            in_stock,
            products.c.rating_avg.desc(),
            products.c.review_count.desc(),
            products.c.id.asc(),
        )

    async def rerank_candidates(self, product_ids: Sequence[int]) -> list[RerankCandidate]:
        if not product_ids:
            return []
        rows = (
            await self._session.execute(
                select(documents.c.product_id, documents.c.document_text).where(
                    documents.c.product_id.in_(list(product_ids))
                )
            )
        ).all()
        by_id = {row.product_id: row.document_text for row in rows}
        return [
            RerankCandidate(product_id=product_id, document_text=by_id[product_id])
            for product_id in product_ids
            if by_id.get(product_id)
        ]

    async def cached_query_vector(self, cache_key: str) -> QueryVectorDTO | None:
        row = (
            await self._session.execute(
                select(
                    query_embeddings.c.embedding,
                    query_embeddings.c.embedding_model,
                    query_embeddings.c.embedding_dimensions,
                )
                .where(
                    query_embeddings.c.cache_key == cache_key,
                    query_embeddings.c.expires_at > func.now(),
                )
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return None
        return QueryVectorDTO(
            values=tuple(float(value) for value in row.embedding),
            slot="",
            embedding_model=row.embedding_model,
            dimensions=row.embedding_dimensions,
        )

    async def store_query_vector(
        self, cache_key: str, vector: QueryVectorDTO, *, language: str, ttl_seconds: int
    ) -> None:
        stmt = (
            pg_insert(query_embeddings)
            .values(
                cache_key=cache_key,
                embedding=list(vector.values),
                embedding_model=vector.embedding_model,
                embedding_dimensions=vector.dimensions,
                language=language,
                expires_at=func.now() + text(f"interval '{int(ttl_seconds)} seconds'"),
            )
            .on_conflict_do_nothing(index_elements=["cache_key"])
        )
        await self._session.execute(stmt)

    async def detect_capabilities(self) -> SearchCapabilities:
        installed = await self._session.scalar(
            text("SELECT count(*) FROM pg_extension WHERE extname = :name"),
            {"name": TRIGRAM_EXTENSION},
        )
        return SearchCapabilities(trigram=bool(installed))

    async def catalog_terms(self) -> CatalogLexiconDTO:
        slugs = (await self._session.execute(select(categories.c.slug))).scalars().all()
        origins = (
            (
                await self._session.execute(
                    select(products.c.origin)
                    .where(products.c.is_archived.is_(False), products.c.origin.is_not(None))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        return CatalogLexiconDTO(category_slugs=list(slugs), origins=list(origins))
