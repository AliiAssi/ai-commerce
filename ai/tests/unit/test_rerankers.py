from __future__ import annotations

import httpx
import pytest

from app.application.dtos.search_dto import SearchIntent
from app.application.rerank.hf_reranker import HuggingFaceReranker
from app.application.rerank.ireranker import (
    ERROR_BAD_REQUEST,
    ERROR_MALFORMED,
    ERROR_QUOTA_EXHAUSTED,
    ERROR_RATE_LIMITED,
    ERROR_UNAUTHORIZED,
    RERANK_APPLIED,
    RERANK_SKIPPED,
    RERANK_UNAVAILABLE,
    IReranker,
    PassthroughReranker,
    RerankCandidate,
    RerankError,
    RerankResult,
    classify_http_error,
)
from app.application.rerank.openrouter_reranker import OpenRouterReranker
from app.application.rerank.reranker_chain import RerankerChain
from app.application.rerank.resilient_reranker import ResilientReranker
from app.core.config import Settings
from app.core.registry import _build_reranker

MOLASSES = RerankCandidate(
    product_id=11,
    document_text=(
        "Name: Pomegranate Molasses\nCategory: Pantry\nOrigin: Bekaa\n"
        "Description: Thick tart syrup reduced from sour pomegranates, the souring agent in "
        "fattoush and muhammara."
    ),
)
BASKET = RerankCandidate(
    product_id=22,
    document_text=(
        "Name: Reed Serving Basket\nCategory: Home\nOrigin: Tripoli\n"
        "Description: Hand-woven reed basket for bread and fruit."
    ),
)
SUMAC = RerankCandidate(
    product_id=33,
    document_text=(
        "Name: Sumac\nCategory: Spices\nOrigin: Akkar\n"
        "Description: Tangy crimson ground sumac berries for salads and fattoush."
    ),
)


def intent(text: str = "شيء حامض للفتوش", *, semantic: str | None = None) -> SearchIntent:
    return SearchIntent(
        original_query=text,
        normalized_query=text,
        semantic_text=text if semantic is None else semantic,
        language="ar",
        parser_version="test-1",
        lexicon_version=1,
    )


def settings(**overrides) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://u:p@localhost/db",
        "INTERNAL_API_KEY": "k" * 32,
        "MCP_BEARER_TOKEN": "t" * 32,
        "OLLAMA_API_KEY": "o" * 32,
        "RERANKER_MODEL": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
        "RERANKER_API_KEY": "secret-key",
    }
    return Settings(**{**base, **overrides})


def transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://example.invalid", transport=httpx.MockTransport(handler)
    )


class TestTheOpenRouterAdapter:
    async def test_it_maps_scores_back_by_index_not_by_position(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": "gen-rerank-1-abc",
                    "model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
                    "usage": {"search_units": 1, "total_tokens": 340},
                    "results": [
                        {"index": 2, "relevance_score": 0.21240908},
                        {"index": 0, "relevance_score": 0.11263894},
                        {"index": 1, "relevance_score": -0.10852146},
                    ],
                },
            )

        adapter = OpenRouterReranker(settings(), transport(handler))
        result = await adapter.rerank(intent(), [MOLASSES, BASKET, SUMAC], window=30)

        assert result.outcome == RERANK_APPLIED
        assert result.product_ids == [SUMAC.product_id, MOLASSES.product_id, BASKET.product_id]

    async def test_it_sends_the_semantic_text_rather_than_the_raw_query(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={"results": [{"index": i, "relevance_score": 0.0} for i in range(2)]},
            )

        parsed = intent("olive oil for frying under $25", semantic="olive oil for frying")
        await OpenRouterReranker(settings(), transport(handler)).rerank(
            parsed, [MOLASSES, BASKET], window=30
        )
        assert captured["query"] == "olive oil for frying"

    async def test_a_spent_allowance_is_not_reported_as_a_bad_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                402,
                json={"error": {"code": 402, "message": "Insufficient credits"}},
            )

        adapter = OpenRouterReranker(settings(), transport(handler))
        with pytest.raises(RerankError) as caught:
            await adapter.rerank(intent(), [MOLASSES, BASKET], window=30)
        assert caught.value.code == ERROR_QUOTA_EXHAUSTED
        assert not caught.value.retryable

    async def test_a_genuinely_rejected_key_is_still_unauthorized(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"code": 401, "message": "No auth"}})

        with pytest.raises(RerankError) as caught:
            await OpenRouterReranker(settings(), transport(handler)).rerank(
                intent(), [MOLASSES, BASKET], window=30
            )
        assert caught.value.code == ERROR_UNAUTHORIZED

    async def test_it_never_leaks_the_provider_s_message(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "key sk-or-abcdef is revoked"}})

        with pytest.raises(RerankError) as caught:
            await OpenRouterReranker(settings(), transport(handler)).rerank(
                intent(), [MOLASSES, BASKET], window=30
            )
        assert "sk-or-abcdef" not in str(caught.value)

    async def test_a_short_result_list_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.9}]})

        with pytest.raises(RerankError) as caught:
            await OpenRouterReranker(settings(), transport(handler)).rerank(
                intent(), [MOLASSES, BASKET, SUMAC], window=30
            )
        assert caught.value.code == ERROR_MALFORMED

    async def test_it_identifies_this_service_to_the_router(self):
        adapter = OpenRouterReranker(settings())
        assert adapter._client.headers["http-referer"] == "https://beit.store"
        assert adapter._client.headers["x-openrouter-title"] == "BEIT"
        await adapter._client.aclose()

    async def test_documents_go_up_as_text_not_images(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured.update(json.loads(request.content))
            return httpx.Response(
                200, json={"results": [{"index": i, "relevance_score": 0.0} for i in range(2)]}
            )

        await OpenRouterReranker(settings(), transport(handler)).rerank(
            intent(), [MOLASSES, BASKET], window=30
        )
        assert captured["documents"] == [MOLASSES.document_text, BASKET.document_text]
        assert captured["top_n"] == 2


class TestTheHuggingFaceAdapter:
    def hf_settings(self):
        return settings(RERANKER_PROVIDER="huggingface", RERANKER_MODEL="BAAI/bge-reranker-v2-m3")

    async def test_it_reads_the_batch_shape_the_live_api_actually_returns(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    [
                        {"label": "LABEL_0", "score": 0.3943418264389038},
                        {"label": "LABEL_0", "score": 0.00009106471406994388},
                        {"label": "LABEL_0", "score": 0.03696860745549202},
                    ]
                ],
            )

        adapter = HuggingFaceReranker(self.hf_settings(), transport(handler))
        result = await adapter.rerank(intent(), [MOLASSES, BASKET, SUMAC], window=30)
        assert result.product_ids == [MOLASSES.product_id, SUMAC.product_id, BASKET.product_id]

    async def test_it_also_reads_the_documented_shape(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    [{"label": "LABEL_0", "score": 0.39}],
                    [{"label": "LABEL_0", "score": 0.0001}],
                    [{"label": "LABEL_0", "score": 0.04}],
                ],
            )

        adapter = HuggingFaceReranker(self.hf_settings(), transport(handler))
        result = await adapter.rerank(intent(), [MOLASSES, BASKET, SUMAC], window=30)
        assert result.product_ids == [MOLASSES.product_id, SUMAC.product_id, BASKET.product_id]

    async def test_it_sends_one_query_document_pair_per_candidate(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured.update(json.loads(request.content))
            return httpx.Response(200, json=[[{"label": "LABEL_0", "score": 0.1}] * 2])

        await HuggingFaceReranker(self.hf_settings(), transport(handler)).rerank(
            intent(), [MOLASSES, BASKET], window=30
        )
        assert captured["inputs"] == [
            {"text": "شيء حامض للفتوش", "text_pair": MOLASSES.document_text},
            {"text": "شيء حامض للفتوش", "text_pair": BASKET.document_text},
        ]

    async def test_an_unreadable_payload_is_malformed_rather_than_a_crash(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": "Model is loading"})

        with pytest.raises(RerankError) as caught:
            await HuggingFaceReranker(self.hf_settings(), transport(handler)).rerank(
                intent(), [MOLASSES, BASKET], window=30
            )
        assert caught.value.code == ERROR_MALFORMED

    async def test_a_spent_monthly_credit_is_quota_not_auth(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json={"error": "You have exceeded your monthly quota"})

        with pytest.raises(RerankError) as caught:
            await HuggingFaceReranker(self.hf_settings(), transport(handler)).rerank(
                intent(), [MOLASSES, BASKET], window=30
            )
        assert caught.value.code == ERROR_QUOTA_EXHAUSTED


class TestOrderingRules:
    async def test_ties_stay_in_the_fused_order(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"results": [{"index": i, "relevance_score": 0.5} for i in range(3)]},
            )

        result = await OpenRouterReranker(settings(), transport(handler)).rerank(
            intent(), [MOLASSES, BASKET, SUMAC], window=30
        )
        assert result.product_ids == [MOLASSES.product_id, BASKET.product_id, SUMAC.product_id]

    async def test_candidates_past_the_window_keep_their_fused_position(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"index": 0, "relevance_score": 0.1},
                        {"index": 1, "relevance_score": 0.9},
                    ]
                },
            )

        result = await OpenRouterReranker(settings(), transport(handler)).rerank(
            intent(), [MOLASSES, BASKET, SUMAC], window=2
        )
        assert result.product_ids == [BASKET.product_id, MOLASSES.product_id, SUMAC.product_id]

    async def test_a_single_candidate_costs_no_provider_call(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("the provider must not be called for one candidate")

        result = await OpenRouterReranker(settings(), transport(handler)).rerank(
            intent(), [MOLASSES], window=30
        )
        assert result.outcome == RERANK_SKIPPED
        assert result.product_ids == [MOLASSES.product_id]

    async def test_the_passthrough_returns_ids_untouched(self):
        result = await PassthroughReranker().rerank(intent(), [MOLASSES, BASKET], window=30)
        assert result.product_ids == [MOLASSES.product_id, BASKET.product_id]
        assert result.outcome == RERANK_SKIPPED
        assert not result.applied


class TestErrorClassification:
    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            (429, "", ERROR_RATE_LIMITED),
            (402, "", ERROR_QUOTA_EXHAUSTED),
            (402, '{"error":{"message":"Insufficient credits"}}', ERROR_QUOTA_EXHAUSTED),
            (403, "Insufficient account balance. Top up", ERROR_QUOTA_EXHAUSTED),
            (403, "forbidden", ERROR_UNAUTHORIZED),
            (401, "", ERROR_UNAUTHORIZED),
            (400, "", ERROR_BAD_REQUEST),
            (503, "", "provider_unavailable"),
        ],
    )
    def test_statuses_map_to_codes(self, status, body, expected):
        exc = httpx.HTTPStatusError(
            "boom",
            request=httpx.Request("POST", "https://example.invalid"),
            response=httpx.Response(status),
        )
        assert classify_http_error(exc, body) == expected

    def test_only_the_transient_half_is_retryable(self):
        assert RerankError("x", code=ERROR_RATE_LIMITED).retryable
        assert not RerankError("x", code=ERROR_QUOTA_EXHAUSTED).retryable
        assert not RerankError("x", code=ERROR_UNAUTHORIZED).retryable


class TestResilience:
    def failing(self, code):
        class _Boom:
            version = "boom-1"

            async def rerank(self, intent, candidates, *, window):
                raise RerankError("failed", code=code)

        return _Boom()

    async def test_a_provider_failure_returns_the_fused_order_rather_than_raising(self):
        wrapped = ResilientReranker(self.failing("provider_unavailable"), settings())
        result = await wrapped.rerank(intent(), [MOLASSES, BASKET], window=30)
        assert result.outcome == RERANK_UNAVAILABLE
        assert result.product_ids == [MOLASSES.product_id, BASKET.product_id]

    async def test_a_spent_allowance_stops_calling_the_provider_at_all(self):
        calls = 0

        class _Spent:
            version = "spent-1"

            async def rerank(self, intent, candidates, *, window):
                nonlocal calls
                calls += 1
                raise RerankError("no balance", code=ERROR_QUOTA_EXHAUSTED)

        wrapped = ResilientReranker(_Spent(), settings())
        for _ in range(5):
            result = await wrapped.rerank(intent(), [MOLASSES, BASKET], window=30)
            assert result.product_ids == [MOLASSES.product_id, BASKET.product_id]
        assert calls == 1, "a spent allowance must be probed once, not once per search"
        assert wrapped.is_open

    async def test_an_ordinary_failure_still_takes_the_configured_threshold(self):
        calls = 0

        class _Flaky:
            version = "flaky-1"

            async def rerank(self, intent, candidates, *, window):
                nonlocal calls
                calls += 1
                raise RerankError("down", code="provider_unavailable")

        wrapped = ResilientReranker(_Flaky(), settings(RERANKER_BREAKER_FAILURES=3))
        for _ in range(5):
            await wrapped.rerank(intent(), [MOLASSES, BASKET], window=30)
        assert calls == 3

    async def test_a_reranker_that_drops_a_product_is_not_trusted(self):
        class _Loses:
            version = "loses-1"

            async def rerank(self, intent, candidates, *, window):
                from app.application.rerank.ireranker import RerankResult

                return RerankResult([candidates[0].product_id], outcome=RERANK_APPLIED)

        wrapped = ResilientReranker(_Loses(), settings())
        result = await wrapped.rerank(intent(), [MOLASSES, BASKET, SUMAC], window=30)
        assert result.outcome == RERANK_UNAVAILABLE
        assert result.product_ids == [MOLASSES.product_id, BASKET.product_id, SUMAC.product_id]

    async def test_a_slow_provider_is_abandoned_at_the_timeout(self):
        import asyncio

        class _Slow:
            version = "slow-1"

            async def rerank(self, intent, candidates, *, window):
                await asyncio.sleep(5)
                raise AssertionError("should have been abandoned")

        wrapped = ResilientReranker(_Slow(), settings(RERANKER_TIMEOUT_SECONDS=0.05))
        result = await wrapped.rerank(intent(), [MOLASSES, BASKET], window=30)
        assert result.outcome == RERANK_UNAVAILABLE
        assert result.product_ids == [MOLASSES.product_id, BASKET.product_id]


class TestTheRegistryWiring:
    def test_no_provider_configured_is_the_passthrough(self):
        built = _build_reranker(settings(RERANKER_PROVIDER=""))
        assert isinstance(built, PassthroughReranker)

    def test_a_configured_provider_is_wrapped_in_its_breaker(self):
        built = _build_reranker(settings(RERANKER_PROVIDER="openrouter"))
        assert isinstance(built, ResilientReranker)
        assert built.version == "openrouter:nvidia/llama-nemotron-rerank-vl-1b-v2:free"

    def test_an_unknown_provider_name_fails_loudly_at_boot(self):
        with pytest.raises(ValueError, match="Unknown primary reranker provider"):
            _build_reranker(settings(RERANKER_PROVIDER="openrouterr"))


class TestTheFallbackChain:
    def working(self, name, order):
        class _Works:
            version = name

            async def rerank(self, intent, candidates, *, window):
                from app.application.rerank.ireranker import RerankResult

                return RerankResult(order, outcome=RERANK_APPLIED, version=name)

        return _Works()

    def declining(self, name):
        class _Declines:
            version = name
            calls = 0

            async def rerank(_self, intent, candidates, *, window):
                _self.calls += 1
                return RerankResult(
                    [c.product_id for c in candidates],
                    outcome=RERANK_UNAVAILABLE,
                    version=name,
                )

        return _Declines()

    async def test_the_primary_answers_and_the_fallback_is_never_called(self):
        second = self.declining("second")
        primary = self.working("first", [SUMAC.product_id, MOLASSES.product_id])
        chain = RerankerChain(primary, second)
        result = await chain.rerank(intent(), [MOLASSES, SUMAC], window=30)
        assert result.product_ids == [SUMAC.product_id, MOLASSES.product_id]
        assert second.calls == 0, "a working primary must not spend the fallback's allowance"

    async def test_a_declining_primary_hands_over_to_the_fallback(self):
        chain = RerankerChain(
            self.declining("first"), self.working("second", [SUMAC.product_id, MOLASSES.product_id])
        )
        result = await chain.rerank(intent(), [MOLASSES, SUMAC], window=30)
        assert result.outcome == RERANK_APPLIED
        assert result.product_ids == [SUMAC.product_id, MOLASSES.product_id]

    async def test_both_declining_leaves_the_fused_order_intact(self):
        chain = RerankerChain(self.declining("first"), self.declining("second"))
        result = await chain.rerank(intent(), [MOLASSES, SUMAC], window=30)
        assert result.outcome == RERANK_UNAVAILABLE
        assert result.product_ids == [MOLASSES.product_id, SUMAC.product_id]
        assert result.version == "first+second"

    async def test_a_deliberate_skip_does_not_wake_the_fallback(self):
        second = self.declining("second")
        chain = RerankerChain(PassthroughReranker(), second)
        result = await chain.rerank(intent(), [MOLASSES, SUMAC], window=30)
        assert result.outcome == RERANK_SKIPPED
        assert second.calls == 0

    async def test_each_leg_keeps_its_own_breaker(self):
        built = _build_reranker(
            settings(
                RERANKER_PROVIDER="huggingface",
                RERANKER_MODEL="BAAI/bge-reranker-v2-m3",
                RERANKER_FALLBACK_PROVIDER="openrouter",
                RERANKER_FALLBACK_MODEL="nvidia/llama-nemotron-rerank-vl-1b-v2:free",
            )
        )
        assert isinstance(built, RerankerChain)
        assert built._primary._breaker is not built._fallback._breaker
        assert built.version == (
            "hf:BAAI/bge-reranker-v2-m3+openrouter:nvidia/llama-nemotron-rerank-vl-1b-v2:free"
        )

    async def test_a_fallback_naming_an_unknown_adapter_fails_at_boot(self):
        with pytest.raises(ValueError, match="Unknown fallback reranker provider"):
            _build_reranker(
                settings(RERANKER_PROVIDER="openrouter", RERANKER_FALLBACK_PROVIDER="nope")
            )


class TestExplicitSortsOwnTheOrdering:
    """§7.5: an explicit sort decides the order, so reranking must not touch it."""

    def build(self, sort):
        from contextlib import asynccontextmanager

        from app.application.dtos.search_dto import RetrievalResult
        from app.application.llm.embedding_providers import EmbeddingProviders
        from app.application.search.parser import IntentParser
        from app.application.services.search_service import SearchService
        from app.core.index_state import IndexCoverage
        from app.core.search_aliases import load_aliases
        from app.infrastructure.irepositories.isearch_repository import ISearchRepository

        seen = {"calls": 0}

        class _Counting(IReranker):
            @property
            def version(self):
                return "counting-1"

            async def rerank(self, intent, candidates, *, window):
                seen["calls"] += 1
                return RerankResult(
                    [c.product_id for c in reversed(candidates)], outcome=RERANK_APPLIED
                )

        class _Repo:
            async def retrieve(self, request):
                return RetrievalResult(product_ids=[3, 1, 2], total=3, page=1, page_size=20)

            async def rerank_candidates(self, product_ids):
                return [
                    RerankCandidate(product_id=i, document_text=f"doc {i}") for i in product_ids
                ]

        class _Scope:
            def resolve(self, interface):
                assert interface is ISearchRepository
                return _Repo()

        @asynccontextmanager
        async def factory():
            yield _Scope()

        aliases = load_aliases()
        coverage = IndexCoverage()
        coverage.ready = True
        service = SearchService(
            IntentParser(aliases),
            aliases,
            EmbeddingProviders(primary=None),
            _Counting(),
            coverage,
            settings(),
            factory,
        )
        return service, seen

    async def query(self, sort):
        from app.application.dtos.search_dto import ExplicitFilters, SearchQuery

        service, seen = self.build(sort)
        result = await service.search(SearchQuery(q="copper", explicit=ExplicitFilters(sort=sort)))
        return result, seen

    async def test_a_price_sort_skips_the_reranker_entirely(self):
        result, seen = await self.query("price_desc")
        assert seen["calls"] == 0, "an explicit sort owns the ordering (§7.5)"
        assert result.product_ids == [3, 1, 2]
        assert result.reranked is False

    async def test_relevance_still_reranks(self):
        result, seen = await self.query("relevance")
        assert seen["calls"] == 1
        assert result.product_ids == [2, 1, 3]
        assert result.reranked is True
