from __future__ import annotations

import logging
import re
from dataclasses import dataclass

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.search_dto import (
    CatalogLexiconDTO,
    EffectiveFilters,
    RetrievalRequest,
    RetrievalResult,
)
from app.application.search.normalizer import fold_for_matching, tokenize
from app.core.config import Settings
from app.core.index_state import IndexCoverage
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.models.search import SearchDocument

logger = logging.getLogger(__name__)

# Bumped from "1" in phase 4: the lexical leg now reads this service's weighted documents rather
# than web's flat products.search_vector, which changes the ordering it produces. §14.5 makes a
# ranking change that cannot be attributed to a version unmeasurable.
RANKER_VERSION = "2"

documents = SearchDocument.__table__

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


def _empty(request: RetrievalRequest) -> RetrievalResult:
    return RetrievalResult(product_ids=[], total=0, page=request.page, page_size=request.page_size)


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
    """Lexical + trigram retrieval fused by RRF, against the catalog the web service owns.

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

    async def _browse(self, request: RetrievalRequest) -> RetrievalResult:
        """No semantic text, so §7.2 skips retrieval entirely and filters the catalog."""
        stmt = self._filtered(request.filters)
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
        )

    # ---- fused retrieval --------------------------------------------------------------------

    async def _fused(self, request: RetrievalRequest) -> RetrievalResult:
        settings = self._settings
        filters = request.filters
        filtered = self._filtered(filters).cte("filtered")

        # Read the gate once. It is mutable process state refreshed by the index worker, and a
        # query that built one leg from step 3 and reported step 4 would be unattributable.
        use_documents = self._coverage.ready
        lex = self._lexical_cte(filtered, request.semantic_text, use_documents=use_documents)
        if lex is None:
            # The semantic text held no usable token at all — so neither can the trigram leg,
            # which reads the same tokens through a length filter. Same rule as an empty fused
            # set below: constraints still answer, a bare unmatchable query does not.
            return await self._browse(request) if filters.has_filters else _empty(request)

        tokens = trigram_tokens(request.semantic_text) if self._capabilities.trigram else []
        trg = self._trigram_cte(filtered, tokens, filters) if tokens else None

        score = self._rrf_score(lex, trg)
        null_rank = literal(None, type_=Integer)
        if trg is None:
            fused_source: Select = select(
                lex.c.id.label("id"),
                score.label("score"),
                lex.c.rank.label("lex_rank"),
                null_rank.label("trg_rank"),
            ).select_from(lex)
        else:
            fused_source = select(
                func.coalesce(lex.c.id, trg.c.id).label("id"),
                score.label("score"),
                lex.c.rank.label("lex_rank"),
                trg.c.rank.label("trg_rank"),
            ).select_from(lex.join(trg, lex.c.id == trg.c.id, full=True))

        # §7.4: below the floor the system returns nothing rather than unrelated neighbours.
        # The floor stays 0.0 until phase 6 calibrates it against the acceptance corpus, where
        # `zzzznotathing` is the case it has to keep empty.
        eligible = fused_source.cte("fused")
        eligible = (
            select(eligible.c.id, eligible.c.score, eligible.c.lex_rank, eligible.c.trg_rank)
            .where(eligible.c.score >= settings.SEARCH_RELEVANCE_FLOOR)
            .cte("eligible")
        )

        # One round trip for the exact total and for which legs contributed. count(col) skips
        # nulls, so the two leg counts fall out of the same scan.
        counts = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count(eligible.c.lex_rank),
                    func.count(eligible.c.trg_rank),
                ).select_from(eligible)
            )
        ).one()
        total, lexical_hits, trigram_hits = counts
        if not total:
            # Neither leg matched. If the shopper expressed a deterministic constraint, that
            # constraint is still a real answer and must be served: `صابون تقليدي من طرابلس`
            # resolves origin Tripoli, and §15.2 requires both Tripoli soaps back even though
            # no Arabic token can match an English catalog lexically (§2.1).
            #
            # This does not soften §7.4's empty-set rule, which is about the relevance floor
            # admitting unrelated neighbours. `zzzznotathing` carries no filter, so it falls
            # through here and correctly stays empty rather than returning the whole catalog.
            return await self._browse(request) if filters.has_filters else _empty(request)

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
            lexical_hits=lexical_hits,
            trigram_hits=trigram_hits,
            documents_used=use_documents,
        )

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

    def _rrf_score(self, lex, trg) -> ColumnElement[float]:
        """Reciprocal rank fusion: weight / (k + rank), summed over the legs that matched.

        §7.2 requires fusion by rank rather than by raw score, because ts_rank and trigram
        similarity are not on comparable scales and adding them directly would let whichever
        leg happens to produce larger numbers decide the ordering.
        """
        k = self._settings.SEARCH_RRF_K
        total = func.coalesce(
            literal(self._settings.SEARCH_RRF_WEIGHT_LEXICAL) / (k + lex.c.rank), 0.0
        )
        if trg is not None:
            total = total + func.coalesce(
                literal(self._settings.SEARCH_RRF_WEIGHT_TRIGRAM) / (k + trg.c.rank), 0.0
            )
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

    # ---- filters -----------------------------------------------------------------------------

    @staticmethod
    def _filtered(filters: EffectiveFilters) -> Select:
        """Every deterministic constraint, applied in SQL as early as §7.2 step 5 requires."""
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
