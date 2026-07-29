from __future__ import annotations

import json

import httpx
import pytest

from app.application.dtos.product_dto import ProductSearchParams
from app.application.services.ai_gateway import AIGateway, RemoteSearchRejected
from app.core.config import Settings

# The search half of the gateway. Its contract is narrow and load-bearing: return a result, or
# return None so the caller serves lexical. It must never raise an outage at the caller, and it
# must never let a partially-understood payload through as if it were a good answer (§12).

OK_BODY = {
    "product_ids": [3, 1, 2],
    "total": 3,
    "page": 1,
    "page_size": 12,
    "query": "olive oil",
    "language": "en",
    "mode": "lexical",
    "reranked": False,
    "effective_sort": "relevance",
    "inferred_filters": {"category": "Olive Oil & Za'atar"},
    "ignored_inferred": [],
    "degraded": True,
    "degraded_reason": "feature_disabled",
    "parser_version": "1",
    "lexicon_version": 1,
    "ranker_version": "1",
}


def _settings(**overrides) -> Settings:
    return Settings(
        DATABASE_URL="postgresql://u:p@h/db",
        JWT_SECRET="x" * 32,
        AI_SERVICE_URL="http://ai.test",
        INTERNAL_API_KEY="internal-key",
        **overrides,
    )


def _gateway(handler, **overrides) -> AIGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AIGateway(_settings(**overrides), client=client)


def _params(**overrides) -> ProductSearchParams:
    return ProductSearchParams(q="olive oil", **overrides)


class TestHappyPath:
    async def test_a_good_response_is_parsed(self):
        result = await _gateway(lambda r: httpx.Response(200, json=OK_BODY)).search(_params())

        assert result is not None
        assert result.product_ids == [3, 1, 2]
        assert result.degraded_reason == "feature_disabled"

    async def test_the_internal_key_is_attached(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["x-internal-key"] == "internal-key"
            return httpx.Response(200, json=OK_BODY)

        assert await _gateway(handler).search(_params()) is not None

    async def test_prices_cross_the_hop_as_strings(self):
        # JSON floats would round $14.50 into something that no longer compares equal in SQL.
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert payload["min_price"] == "14.50"
            assert payload["max_price"] == "30.00"
            return httpx.Response(200, json=OK_BODY)

        from decimal import Decimal

        await _gateway(handler).search(
            _params(min_price=Decimal("14.50"), max_price=Decimal("30.00"))
        )

    async def test_explicit_filters_are_forwarded(self):
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert payload["category"] == "ceramics"
            assert payload["origin"] == "tripoli"
            assert payload["in_stock_only"] is True
            assert payload["ignore_inferred"] == ["origin"]
            return httpx.Response(200, json=OK_BODY)

        await _gateway(handler).search(
            _params(
                category_slug="ceramics",
                origin="tripoli",
                in_stock_only=True,
                ignore_inferred=("origin",),
            )
        )

    async def test_an_unset_sort_is_sent_as_null(self):
        # §9.1's conditional default belongs to the AI service, which knows whether a semantic
        # remainder exists. Web must not pre-resolve it into "relevance" here.
        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["sort"] is None
            return httpx.Response(200, json=OK_BODY)

        await _gateway(handler).search(_params())


class TestDegradesToNone:
    async def test_unreachable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        assert await _gateway(handler).search(_params()) is None

    async def test_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        assert await _gateway(handler).search(_params()) is None

    @pytest.mark.parametrize("status", [401, 500, 502, 503, 504])
    async def test_error_statuses(self, status: int):
        result = await _gateway(lambda r: httpx.Response(status, json={})).search(_params())

        assert result is None

    async def test_a_body_that_is_not_json(self):
        result = await _gateway(lambda r: httpx.Response(200, text="<html>oops")).search(_params())

        assert result is None

    async def test_a_response_missing_required_fields(self):
        # A half-populated page is worse than the fallback, because it looks like an answer.
        partial = {"product_ids": [1], "total": 1}
        result = await _gateway(lambda r: httpx.Response(200, json=partial)).search(_params())

        assert result is None

    async def test_a_response_with_an_unknown_mode(self):
        body = {**OK_BODY, "mode": "telepathic"}
        result = await _gateway(lambda r: httpx.Response(200, json=body)).search(_params())

        assert result is None

    async def test_a_degraded_reason_outside_the_enum_is_refused(self):
        # §9.2 makes this a closed enum precisely so an unexpected value is not passed through
        # to the storefront and rendered.
        body = {**OK_BODY, "degraded_reason": "ollama_connection_refused"}
        result = await _gateway(lambda r: httpx.Response(200, json=body)).search(_params())

        assert result is None


class TestValidationPassthrough:
    async def test_a_422_is_surfaced_not_swallowed(self):
        # A contradictory price range is the shopper's to fix. Serving the fallback would hide
        # a real validation error behind results that ignore half their query (§15.3).
        body = {"error": {"code": "invalid_search", "message": "min is above max"}}

        with pytest.raises(RemoteSearchRejected) as caught:
            await _gateway(lambda r: httpx.Response(422, json=body)).search(_params())

        assert caught.value.status_code == 422
        assert "min is above max" in caught.value.message

    async def test_a_422_without_a_usable_body_still_reads_sensibly(self):
        with pytest.raises(RemoteSearchRejected) as caught:
            await _gateway(lambda r: httpx.Response(422, json=[])).search(_params())

        assert caught.value.message


class TestTimeoutBudget:
    async def test_search_uses_its_own_timeout_not_the_chat_one(self):
        # The client-wide timeout is sized for a chat stream waiting out a cold boot. §14.2
        # gives the whole catalog request 3 seconds.
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json=OK_BODY)

        await _gateway(handler, SEARCH_TIMEOUT_SECONDS=2.5).search(_params())

        assert seen["timeout"]["read"] == 2.5
