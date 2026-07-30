from __future__ import annotations

import logging
import re
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
from app.application.search.normalizer import fold_for_matching, tokenize
from app.core.config import Settings
from app.core.index_state import IndexCoverage
from app.core.vector_schema import FALLBACK_SLOT, PRIMARY_SLOT
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.models.search import SearchDocument, SearchQueryEmbedding

logger = logging.getLogger(__name__)

# Bumped from "2" in phase 6: a semantic leg joins the fusion, which changes the ordering for
# every query that has one. §14.5 makes a ranking change that cannot be attributed to a version
# unmeasurable.
RANKER_VERSION = "3"

documents = SearchDocument.__table__
query_embeddings = SearchQueryEmbedding.__table__

# Which column each embedding slot reads. The mapping is duplicated from the index repository
# rather than shared, because these are the two places that may name a vector column and a shared
# helper between two repositories would be a coupling neither needs.
_SLOT_COLUMN = {
    PRIMARY_SLOT: documents.c.embedding,
    FALLBACK_SLOT: documents.c.fallback_embedding,
}

# The trigram leg's only hard dependency. Named here so both the startup probe and the runtime
# recovery below agree on what they are looking for.
TRIGRAM_EXTENSION = "pg_trgm"


# Why there is no in-request recovery from a missing extension:
#
# Postgres aborts the whole transaction on a failed statement, so nothing else can run on that
# session afterwards. Catching the error and retrying without the trigram leg would need a
# SAVEPOINT taken *before* every search — a round trip on the hot path, forever, to insure
# against a condition the startup probe already rules out.
#
# So the capability is settled at boot instead, and a `word_similarity` error that somehow
# still escapes is left to surface. The shopper is not exposed to it either way: web's gateway
# turns any non-200 from this service into its own lexical fallback (§12), so a 500 here costs
# result quality for one request, not a broken store.


# Trigram matching earns its place on transliterated names — rakwe/rakweh, za'atar/zaatar — so
# it is fed word-sized tokens rather than the whole query. Below four characters a trigram
# comparison is mostly noise; past a handful of tokens the scan cost grows for no recall.
_MIN_TRIGRAM_TOKEN = 4
_MAX_TRIGRAM_TOKENS = 8

# to_tsquery parses its argument as an expression, so anything that could read as an operator
# has to go. The tokenizer has already removed most of it; apostrophes are what is left.
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
    """Tokens for the OR-joined tsquery, stripped to what to_tsquery will accept."""
    tokens = [_TSQUERY_UNSAFE.sub("", token) for token in tokenize(semantic_text)]
    return list(dict.fromkeys(token for token in tokens if token))


def _tied_rank(ranked):
    """RRF rank for one leg — `rank()`, deliberately not `row_number()`.

    Equally relevant documents must receive the same rank. `row_number()` would break the tie
    on whatever the ordering falls back to (product id), and that arbitrary choice would then
    survive fusion as a real score difference — leaving §7.4's later rules, in particular
    "in-stock before out-of-stock when semantic relevance is otherwise equivalent", with no tie
    left to break. Ranking is also how RRF is actually defined.
    """
    return func.rank().over(order_by=ranked.c.score.desc())


def _empty(request: RetrievalRequest, *, semantic_used: bool = False) -> RetrievalResult:
    """No results, and whether a semantic leg was among the things that found none.

    `semantic_used` has to be carried even here — especially here. Found in the live smoke test:
    `zzzznotathing` correctly returned nothing, and reported `degraded: true` with
    `index_incomplete`, because the empty path dropped the flag and the caller could only
    conclude the semantic leg never ran. That is an operator being sent to look at a healthy
    index because search worked. A semantic search that runs and honestly finds nothing is not
    degraded; it is §7.4 doing its job.
    """
    return RetrievalResult(
        product_ids=[],
        total=0,
        page=request.page,
        page_size=request.page_size,
        semantic_used=semantic_used,
    )


def filtered_products(filters: EffectiveFilters) -> Select:
    """Every deterministic constraint, applied in SQL as early as §7.2 step 5 requires.

    Module-level and public because this is the definition of *which products a query may
    return*, and more than the repository has to agree with it: the embedding bake-off scores
    candidates inside the same filtered set, because a semantic leg never overrules a filter
    (§7.3) and crediting a model for work SQL already did would measure the wrong thing.
    """
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
    """Optional database features retrieval will use if they are there.

    One shared, mutable instance for the process, settled by the startup probe. `pg_trgm` is
    created by the *web* service's migrations — the trigram indexes sit on web's `products`
    table — so this service can perfectly well be pointed at a database that does not have it
    yet, and it has to answer anyway.

    Defaults to true so a database that was unreachable at boot is assumed capable rather than
    silently downgraded.
    """

    trigram: bool = True


class SearchRepository(ISearchRepository):
    """Semantic + lexical + trigram retrieval fused by RRF, against the catalog web owns.

    The semantic leg is the one that can be absent. It runs only when the caller supplied a query
    vector *and* the column that vector belongs to is populated enough to read; otherwise fusion
    is exactly the two-leg shape phase 4 shipped, which is §12's step 3. Nothing else changes
    when it is missing, which is what makes an embedding outage a narrower answer rather than a
    different system.

    §12's ladder gives the lexical leg two sources, and which one runs is decided by index
    coverage rather than by configuration. Step 3 is this service's `ai_search_documents`, whose
    documents carry the category and origin that web's `products.search_vector` — a generated
    column over name and description only — cannot, and a second `simple` vector that gives
    Arabic its only lexical route (§2.1). Step 4 is that generated column, which is always
    populated and therefore always able to answer.

    The trigram leg reads `products` under both, deliberately. Its `gin_trgm_ops` indexes belong
    to web and sit on the same two strings the document copies, so moving it would mean building
    a second set of indexes over identical data to satisfy a literal reading of step 3.
    """

    # Neither `capabilities` nor `coverage` is `... | None`. The container resolves constructor
    # dependencies by their exact annotation, so a union would never match the bound instance —
    # it would silently fall back to a private default, and switching either one off would then
    # last exactly one request.
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

    # ---- filtered browse --------------------------------------------------------------------

    async def _browse(
        self, request: RetrievalRequest, *, semantic_used: bool = False
    ) -> RetrievalResult:
        """No semantic text, so §7.2 skips retrieval entirely and filters the catalog.

        Also reached as the constraint fallback when fusion matched nothing but the shopper
        expressed a real filter, which is why it carries `semantic_used`: that call did run a
        semantic leg, and reporting otherwise would blame the index for an empty match.
        """
        stmt = filtered_products(request.filters)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery("filtered_count"))
        )
        # `relevance` has nothing to rank here; §9.1 makes newest the default without a query
        # and that is what a pure constraint list is.
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

    # ---- fused retrieval --------------------------------------------------------------------

    async def _fused(self, request: RetrievalRequest) -> RetrievalResult:
        settings = self._settings
        filters = request.filters
        filtered = filtered_products(filters).cte("filtered")

        # Read the gate once. It is mutable process state refreshed by the index worker, and a
        # query that built one leg from step 3 and reported step 4 would be unattributable.
        use_documents = self._coverage.ready
        lex = self._lexical_cte(filtered, request.semantic_text, use_documents=use_documents)
        sem = await self._semantic_cte(filtered, request.query_vector)
        semantic_used = sem is not None
        if lex is None and sem is None:
            # The semantic text held no usable token at all — so neither can the trigram leg,
            # which reads the same tokens through a length filter. Same rule as an empty fused
            # set below: constraints still answer, a bare unmatchable query does not.
            return (
                await self._browse(request, semantic_used=semantic_used)
                if filters.has_filters
                else _empty(request, semantic_used=semantic_used)
            )

        tokens = trigram_tokens(request.semantic_text) if self._capabilities.trigram else []
        trg = self._trigram_cte(filtered, tokens, filters) if tokens else None

        legs = {"sem": sem, "lex": lex, "trg": trg}
        eligible = self._fuse(legs).cte("fused")
        # §7.4: below the floor the system returns nothing rather than unrelated neighbours.
        eligible = (
            select(*eligible.c)
            .where(eligible.c.score >= settings.SEARCH_RELEVANCE_FLOOR)
            .cte("eligible")
        )

        # One round trip for the exact total and for which legs contributed. count(col) skips
        # nulls, so every leg count falls out of the same scan.
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
            # Neither leg matched. If the shopper expressed a deterministic constraint, that
            # constraint is still a real answer and must be served: `صابون تقليدي من طرابلس`
            # resolves origin Tripoli, and §15.2 requires both Tripoli soaps back even though
            # no Arabic token can match an English catalog lexically (§2.1).
            #
            # This does not soften §7.4's empty-set rule, which is about the relevance floor
            # admitting unrelated neighbours. `zzzznotathing` carries no filter, so it falls
            # through here and correctly stays empty rather than returning the whole catalog.
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

    # ---- fusion ------------------------------------------------------------------------------

    def _fuse(self, legs: dict[str, object]) -> Select:
        """Chain whichever legs are present into one FULL OUTER JOIN and sum their RRF terms.

        Built by folding rather than by branching. Two optional legs was two cases and could be
        written out; three is eight, and the seventh would be the one nobody exercised. Every leg
        contributes a `<name>_rank` column that is NULL when it did not return the product, which
        is also what makes the per-leg hit counts a single `count(col)` on the same scan.

        The join condition accumulates a COALESCE over the ids already joined, which is what a
        chain of full outer joins needs: after the first join either side can be NULL, so joining
        the next leg against only one of them would drop every row the other leg found alone —
        and for Arabic the semantic leg is routinely the only one that found anything (§2.1).
        """
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

    # ---- the semantic leg ----------------------------------------------------------------------

    async def _semantic_cte(self, filtered, query_vector: QueryVectorDTO | None):
        """Nearest neighbours by cosine distance, above a calibrated similarity floor (§7.2).

        Returns None — and the query falls back to exactly its phase-4 behaviour — when there is
        no vector, or when the column this vector belongs to is not populated enough to read.
        Both are §12 degradations, and the second is the one worth naming: running the semantic
        leg over a half-filled column would rank whichever products happen to be embedded above
        products that simply have not been reached yet, which reads as a relevance bug and is an
        indexing one.

        **The similarity threshold is where §7.4's empty-set rule lives.** `SEARCH_RELEVANCE_FLOOR`
        over the fused RRF score cannot do it: rank 1 scores `weight/(k+1)` whether the neighbour
        is the right product or the only product in a catalog of unrelated things, so
        `zzzznotathing` would arrive with a perfect fused score. Cosine similarity is the only
        signal in the pipeline that can say "and this one is bad", so it is what the corpus
        calibrates.

        The threshold cannot be replaced by "require a second leg to agree" either. Arabic has no
        lexical leg at all against an English catalog (§2.1), so semantic-only candidates are
        exactly the ones this phase exists to admit.
        """
        if query_vector is None or not self._coverage.semantic(query_vector.slot):
            return None
        column = _SLOT_COLUMN.get(query_vector.slot)
        if column is None:
            return None

        # §14.3 requires the HNSW parameters to be tunable, and §7.4 forbids an approximate index
        # letting a filtered query under-return without detection. `iterative_scan` is what makes
        # pgvector keep scanning when the filter rejects most of what the index handed back;
        # relaxed order is enough because RRF and §7.4's tie-breakers re-establish the ordering
        # anyway.
        #
        # `set_config(..., is_local => true)` rather than two SET LOCAL statements: it is
        # transaction-local in exactly the same way, it fits in one round trip on the hot path,
        # and its arguments are ordinary bound parameters. Two SET LOCALs cannot be sent
        # together — asyncpg prepares every statement and Postgres refuses multiple commands in
        # a prepared statement — and SET LOCAL takes no parameters at all, so the values would
        # have to be interpolated into SQL.
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
        # Cosine *similarity*, so the threshold reads the way the corpus talks about it and 1.0
        # is a perfect match rather than a perfect mismatch.
        similarity = literal(1.0) - distance
        ranked = (
            select(documents.c.product_id.label("id"), similarity.label("score"))
            .select_from(documents.join(filtered, filtered.c.id == documents.c.product_id))
            .where(
                column.is_not(None),
                similarity >= self._settings.SEARCH_SEMANTIC_MIN_SIMILARITY,
            )
            # ORDER BY distance with a LIMIT, in the form the HNSW index can serve (§14.3).
            .order_by(distance.asc(), documents.c.product_id.asc())
            .limit(self._settings.SEARCH_SEMANTIC_CANDIDATES)
            .subquery("semantic_ranked")
        )
        return select(ranked.c.id, _tied_rank(ranked).label("rank")).cte("sem")

    # ---- the lexical leg, on either of §12's two sources ---------------------------------------

    def _lexical_cte(self, filtered, semantic_text: str, *, use_documents: bool):
        """Full-text candidates, ranked by ts_rank over an OR of the query's terms.

        `websearch_to_tsquery` — what the storefront's own search uses — ANDs its terms, so
        `traditional soap from Tripoli` matches nothing unless a product contains all four
        words. That is the right contract for a single-strategy search and the wrong one for a
        leg of a fused set, where this leg exists to contribute *candidates*. OR-ing the terms
        restores recall without costing precision at the top, because ts_rank already scores a
        document matching more of the query above one matching less of it.

        Both sources rank into the same shape, so fusion downstream cannot tell them apart.
        """
        tokens = lexical_tokens(semantic_text)
        if not tokens:
            return None
        if use_documents:
            return self._document_lexical_cte(filtered, tokens)
        return self._catalog_lexical_cte(filtered, " | ".join(tokens))

    def _document_lexical_cte(self, filtered, tokens: list[str]):
        """§12 step 3 — this service's documents, both vectors, weighted by field.

        The two vectors are queried together rather than chosen between by detected language.
        `search_vector_en` is stemmed and answers English prose; `search_vector_simple` is not
        stemmed, which is what Arabic, mixed text and exact product names need (§10.2). Taking
        the greater of the two ranks means no language has to be passed into retrieval at all,
        and a query that is English apart from one Arabic word still matches on both halves.

        Membership still comes from `filtered`, which is built over `products` — so an archived
        product cannot reach a shopper through a document the prune has not caught up with yet.
        """
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
        """§12 step 4 — web's generated `products.search_vector`.

        Flat, English-stemmed, and over name and description only, so it knows nothing about
        category or origin. That is exactly why it is the fallback and not the default; it is
        also why it can never be empty, which is what makes it safe to fall back *to*.
        """
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
        """The query's tokens with English stopwords removed, as a `to_tsquery` expression.

        The `simple` dictionary does no stemming, which is the point of it — and it also has no
        stopword list, which is not. Feeding it the query verbatim makes `for` and `the` into
        ordinary searchable lexemes, so `sour ingredient for fattoush` matches every product
        whose description happens to say "for" and ranks a reed basket above the pomegranate
        molasses. Caught by running the §15 corpus against both rungs; it is invisible on
        `products.search_vector`, which is English-configured and drops these itself.

        Filtered by Postgres rather than by a stopword list of ours: `to_tsvector('english', t)`
        is empty for exactly the words the English configuration would have discarded, so the
        two rungs agree on what counts as content without either one owning a copy of the list.
        It is a scalar subquery over an array of at most a handful of tokens — no table, no
        index, and no extra round trip. Arabic tokens are not English stopwords and survive
        untouched, which is what keeps this from quietly disabling the leg for Arabic.
        """
        token = func.unnest(
            bindparam("lexical_tokens", value=tokens, type_=ARRAY(String))
        ).column_valued("lexical_token")
        return (
            select(func.string_agg(token, literal(" | ")))
            .where(func.length(func.to_tsvector("english", token)) > 0)
            .scalar_subquery()
        )

    def _rank_weights(self):
        """ts_rank's weight vector, in Postgres's fixed {D, C, B, A} order.

        The index worker labels name lexemes A, category and origin B, and description D, so
        these decide how much each part of a document counts. They are query-side: retuning them
        is a config change, not a reindex. Nothing is labelled C — it is present because
        `ts_rank` requires exactly four elements — so it takes the description's weight, where
        an accidentally unlabelled lexeme would do least harm.
        """
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
        """Greatest word-similarity of any query token against the name or the origin.

        `word_similarity(token, text)` scores a token against the closest extent inside the
        text, which is what makes "rakwe" find "Hammered Copper Rakwe" — plain `similarity()`
        compares whole strings and would score that pair near zero.

        This form cannot use the GIN trigram index, because the threshold is configuration
        rather than the session's `pg_trgm.similarity_threshold`. At the current catalog size
        that is a rounding error; §14.3's 10k target is where it gets revisited.
        """
        token = func.unnest(
            bindparam("trigram_tokens", value=tokens, type_=ARRAY(String))
        ).column_valued("candidate_token")

        targets = [func.word_similarity(token, products.c.name)]
        # Origin joins the comparison only when it is not already a filter. Otherwise the place
        # name in the query scores every surviving product identically — `... from south
        # Lebanon` would rate a jar of za'atar from Jezzine as highly as the glassware the
        # shopper asked for, purely because both carry "South Lebanon" in the column that was
        # used to select them in the first place.
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
        """Reciprocal rank fusion: weight / (k + rank), summed over the legs that matched.

        §7.2 requires fusion by rank rather than by raw score, because cosine similarity, ts_rank
        and trigram similarity are not on comparable scales and adding them directly would let
        whichever leg happens to produce larger numbers decide the ordering.

        Note what this means for the relevance floor. Every leg's best result scores
        `weight/(k+1)` regardless of how good it is, so the fused score cannot express "nothing
        here is relevant" — that judgement has to be made on similarity, inside the semantic leg,
        before ranks exist. See `_semantic_cte`.
        """
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
        """§7.4's priority ladder, restricted to the rules that exist in phase 1.

        Priority 2 (AI-reranked order) has no implementation until phase 7, and until then
        priority 3 — the RRF score — is what orders the page. An explicit non-relevance sort
        owns ordering outright per §7.5; membership still comes from retrieval and filters.
        """
        exact_name = case(
            (func.lower(func.trim(products.c.name)) == request.normalized_query, 1), else_=0
        ).desc()

        if request.filters.sort != "relevance":
            # Exact-name products stay pinned: §7.4 makes that rule unconditional except when
            # an explicit filter excludes the product, which the filters have already done.
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

    # ---- the query-embedding cache (§10.4) -----------------------------------------------------

    async def cached_query_vector(self, cache_key: str) -> QueryVectorDTO | None:
        """A live cached embedding, or None.

        Expiry is checked in the predicate rather than by trusting the prune to have run. The
        prune is a housekeeping job on an hourly clock; correctness cannot wait on it, and a row
        served past its TTL would be a vector built by a model or normalizer that may since have
        changed.
        """
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
            # The slot is not stored: the key already contains the model, so a row can only ever
            # be found by the client that produced it, and the caller knows which slot that was.
            slot="",
            embedding_model=row.embedding_model,
            dimensions=row.embedding_dimensions,
        )

    async def store_query_vector(
        self, cache_key: str, vector: QueryVectorDTO, *, language: str, ttl_seconds: int
    ) -> None:
        # DO NOTHING rather than DO UPDATE: two concurrent shoppers typing the same query would
        # otherwise deadlock-race to rewrite an identical row. The key covers the model and the
        # normalizer version, so an existing row cannot disagree with this one about anything
        # except how long it has left.
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
        # Archived products are excluded: an origin that only survives on a withdrawn product
        # is not something the lexicon has to keep an alias for.
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
