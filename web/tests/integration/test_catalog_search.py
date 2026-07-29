from __future__ import annotations

import os

import pytest

# Routing and fallback for the public catalog. The fallback is the deliverable of this phase:
# every way the AI service can let us down has to land on the same lexical path, with a 200 and
# without a provider detail reaching the shopper (§12).

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


class FakeSearchGateway:
    """Stands in for the AI service. `result` None means "could not answer"."""

    def __init__(self, result=None, raises: Exception | None = None) -> None:
        self.result = result
        self.raises = raises
        self.calls: list = []

    async def search(self, params):
        self.calls.append(params)
        if self.raises is not None:
            raise self.raises
        return self.result

    async def open_chat(self, message, session_id, user_email):  # pragma: no cover
        raise NotImplementedError

    async def warm(self) -> None:  # pragma: no cover
        pass

    async def aclose(self) -> None:
        pass


def _remote(product_ids, **overrides):
    from app.application.dtos.ai_dto import RemoteSearchResult

    body = {
        "product_ids": product_ids,
        "total": len(product_ids),
        "page": 1,
        "page_size": 12,
        "query": "tent",
        "language": "en",
        "mode": "lexical",
        "reranked": False,
        "effective_sort": "relevance",
        "inferred_filters": {},
        "ignored_inferred": [],
        "degraded": True,
        "degraded_reason": "feature_disabled",
    }
    return RemoteSearchResult.model_validate({**body, **overrides})


@pytest.fixture
def routing(client):
    """Enable routing and bind a fake gateway; restore both afterwards."""
    from app.application.iservices.iai_gateway import IAIGateway
    from app.core.config import Settings
    from app.core.container import container

    settings = container.resolve(Settings)
    original = settings.SMART_SEARCH_ROUTING_ENABLED

    def enable(gateway: FakeSearchGateway, *, enabled: bool = True) -> FakeSearchGateway:
        settings.SMART_SEARCH_ROUTING_ENABLED = enabled
        container.bind_instance(IAIGateway, gateway)
        return gateway

    yield enable

    settings.SMART_SEARCH_ROUTING_ENABLED = original
    container._instances.pop(IAIGateway, None)


class TestRoutingDisabled:
    async def test_search_stays_lexical_and_never_calls_the_ai_service(
        self, client, catalog, routing
    ):
        gateway = routing(FakeSearchGateway(), enabled=False)

        body = (await client.get("/api/v1/products", params={"q": "tent"})).json()

        assert gateway.calls == []
        assert body["search"]["mode"] == "lexical"
        # Both match the tsvector: one by name, one by a description mentioning tents.
        assert sorted(item["name"] for item in body["items"]) == ["Alpha Tent", "Gamma Lantern"]

    async def test_a_disabled_route_is_not_reported_as_degraded(self, client, catalog, routing):
        # Nothing failed. The store is configured to serve its own search, and saying
        # "degraded" here would train the storefront to show a warning permanently.
        routing(FakeSearchGateway(), enabled=False)

        body = (await client.get("/api/v1/products", params={"q": "tent"})).json()

        assert body["search"]["degraded"] is False
        assert body["search"]["degraded_reason"] is None


class TestBrowse:
    async def test_an_empty_query_never_reaches_the_ai_service(self, client, catalog, routing):
        # §5.1: browsing is not searching. This also keeps the front page alive while the AI
        # service is asleep.
        gateway = routing(FakeSearchGateway(_remote([1])))

        body = (await client.get("/api/v1/products")).json()

        assert gateway.calls == []
        assert body["search"]["mode"] == "browse"
        assert body["total"] == 3

    async def test_a_whitespace_only_query_is_browsing(self, client, catalog, routing):
        gateway = routing(FakeSearchGateway(_remote([1])))

        body = (await client.get("/api/v1/products", params={"q": "   "})).json()

        assert gateway.calls == []
        assert body["search"]["mode"] == "browse"

    async def test_browse_defaults_to_newest_not_relevance(self, client, catalog, routing):
        routing(FakeSearchGateway(), enabled=False)

        body = (await client.get("/api/v1/products")).json()

        assert body["search"]["effective_sort"] == "newest"


class TestRoutedSearch:
    async def test_the_ai_services_ordering_is_preserved(self, client, catalog, routing):
        # The order is the answer. Re-sorting by any column here would discard the ranking.
        ranked = [catalog["gamma"].id, catalog["alpha"].id, catalog["beta"].id]
        routing(FakeSearchGateway(_remote(ranked)))

        body = (await client.get("/api/v1/products", params={"q": "tent"})).json()

        assert [item["id"] for item in body["items"]] == ranked

    async def test_search_metadata_is_passed_through(self, client, catalog, routing):
        routing(
            FakeSearchGateway(
                _remote(
                    [catalog["alpha"].id],
                    inferred_filters={"max_price": "30"},
                    ignored_inferred=["origin"],
                    language="ar",
                    effective_sort="relevance",
                )
            )
        )

        body = (await client.get("/api/v1/products", params={"q": "tent"})).json()

        assert body["search"]["inferred_filters"] == {"max_price": "30"}
        assert body["search"]["ignored_inferred"] == ["origin"]
        assert body["search"]["language"] == "ar"

    async def test_explicit_filters_reach_the_gateway(self, client, catalog, routing):
        gateway = routing(FakeSearchGateway(_remote([])))

        await client.get(
            "/api/v1/products",
            params={
                "q": "tent",
                "category": "gear",
                "origin": "Beirut",
                "min_price": "10",
                "max_price": "50",
                "in_stock_only": "true",
                "sort": "price_asc",
            },
        )
        sent = gateway.calls[0]

        assert sent.category_slug == "gear"
        assert sent.origin == "Beirut"
        assert sent.in_stock_only is True
        assert sent.sort == "price_asc"

    async def test_an_archived_product_in_the_ranking_is_dropped(self, client, catalog, routing):
        # The AI service filtered archived rows a moment earlier; this is the query whose
        # result actually reaches the shopper.
        from sqlalchemy import text

        from app.core.container import container

        async with container.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE products SET is_archived = true WHERE id = :id"),
                {"id": catalog["beta"].id},
            )
        routing(FakeSearchGateway(_remote([catalog["beta"].id, catalog["alpha"].id])))

        body = (await client.get("/api/v1/products", params={"q": "tent"})).json()

        assert [item["id"] for item in body["items"]] == [catalog["alpha"].id]

    async def test_unknown_ids_do_not_break_the_page(self, client, catalog, routing):
        routing(FakeSearchGateway(_remote([999_999, catalog["alpha"].id])))

        response = await client.get("/api/v1/products", params={"q": "tent"})

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [catalog["alpha"].id]


class TestFallback:
    @pytest.mark.parametrize(
        "gateway",
        [
            FakeSearchGateway(None),  # unreachable, error status, or malformed
        ],
    )
    async def test_an_unanswerable_gateway_serves_lexical(self, client, catalog, routing, gateway):
        routing(gateway)

        response = await client.get("/api/v1/products", params={"q": "tent"})
        body = response.json()

        assert response.status_code == 200
        assert body["search"]["mode"] == "lexical"
        assert body["search"]["degraded"] is True
        # An outage, not a configuration choice — §13 has to be able to tell them apart.
        assert body["search"]["degraded_reason"] == "search_unavailable"
        assert sorted(item["name"] for item in body["items"]) == ["Alpha Tent", "Gamma Lantern"]

    async def test_a_gateway_outage_never_returns_a_500(self, client, catalog, routing):
        # §12: a provider failure must not return HTTP 500 when lexical search can run.
        routing(FakeSearchGateway(None))

        response = await client.get("/api/v1/products", params={"q": "tent"})

        assert response.status_code == 200

    async def test_the_fallback_preserves_deterministic_filters(self, client, catalog, routing):
        # §12: fallback must preserve all explicit filters. Losing them would widen the result
        # set at the exact moment the shopper is least likely to notice.
        routing(FakeSearchGateway(None))

        body = (
            await client.get("/api/v1/products", params={"q": "camping", "max_price": "30"})
        ).json()

        assert [item["name"] for item in body["items"]] == ["Beta Stove"]

    async def test_no_provider_detail_reaches_the_shopper(self, client, catalog, routing):
        # §12: customer-facing copy must not expose "Ollama", "pgvector", keys, or exceptions.
        routing(FakeSearchGateway(None))

        text = (await client.get("/api/v1/products", params={"q": "tent"})).text.lower()

        for leak in ("ollama", "pgvector", "traceback", "httpx", "internal-key"):
            assert leak not in text

    async def test_a_rejected_query_is_surfaced_as_a_validation_error(
        self, client, catalog, routing
    ):
        # §9.3: rejection is not degradation. Quietly serving the fallback would return
        # results that ignore half the query, which is what §15.3 exists to prevent.
        from app.application.services.ai_gateway import RemoteSearchRejected

        routing(FakeSearchGateway(raises=RemoteSearchRejected({"error": {"message": "bad range"}})))

        response = await client.get(
            "/api/v1/products", params={"q": "under $20", "min_price": "25"}
        )

        assert response.status_code == 422

    async def test_a_rejected_query_is_not_reported_as_degraded(self, client, catalog, routing):
        # §9.3: nothing degraded — the request was answerable and was answered.
        from app.application.services.ai_gateway import RemoteSearchRejected

        routing(
            FakeSearchGateway(
                raises=RemoteSearchRejected(
                    {
                        "error": {
                            "message": "The minimum price (25) is higher than the maximum (20).",
                            "details": {"min_price": "25", "max_price": "20"},
                        }
                    }
                )
            )
        )

        body = (
            await client.get("/api/v1/products", params={"q": "under $20", "min_price": "25"})
        ).json()

        assert "search" not in body
        assert "degraded" not in str(body)
        # §9.3 also requires the error to identify which constraint conflicts, so the shopper
        # can correct it rather than guess.
        assert body["error"]["details"] == {"min_price": "25", "max_price": "20"}
        assert "minimum price" in body["error"]["message"]


class TestTransactionDiscipline:
    async def test_no_connection_is_held_while_the_ai_service_is_called(
        self, client, catalog, routing
    ):
        """§8.2: no transaction or checked-out connection may be open across the hop.

        This is the requirement `ScopeFactory` exists for, and the one most likely to be
        undone by a later refactor that switches the handler back to `Injected(...)` — which
        would open a request-long transaction before the handler body ever runs. A slow AI
        service would then pin a connection from a small pool for the whole call, and enough
        concurrent searches would exhaust it.
        """
        from app.core.container import container

        observed: list[int] = []

        class WatchingGateway(FakeSearchGateway):
            async def search(self, params):
                observed.append(container.engine.pool.checkedout())
                return await super().search(params)

        routing(WatchingGateway(_remote([catalog["alpha"].id])))

        await client.get("/api/v1/products", params={"q": "tent"})

        assert observed == [0]


class TestIgnoreInferredParsing:
    async def test_a_repeated_parameter(self, client, catalog, routing):
        gateway = routing(FakeSearchGateway(_remote([])))

        await client.get("/api/v1/products?q=tent&ignore_inferred=origin&ignore_inferred=sort")

        assert gateway.calls[0].ignore_inferred == ("origin", "sort")

    async def test_a_comma_separated_parameter(self, client, catalog, routing):
        gateway = routing(FakeSearchGateway(_remote([])))

        await client.get("/api/v1/products?q=tent&ignore_inferred=origin,sort")

        assert gateway.calls[0].ignore_inferred == ("origin", "sort")

    async def test_duplicates_collapse(self, client, catalog, routing):
        gateway = routing(FakeSearchGateway(_remote([])))

        await client.get("/api/v1/products?q=tent&ignore_inferred=origin,origin")

        assert gateway.calls[0].ignore_inferred == ("origin",)

    async def test_an_unknown_name_does_not_reject_the_request(self, client, catalog, routing):
        # §9.1: a stale bookmark must not 422.
        routing(FakeSearchGateway(_remote([])))

        response = await client.get("/api/v1/products?q=tent&ignore_inferred=nonsense")

        assert response.status_code == 200


class TestContractStability:
    async def test_the_existing_page_fields_are_unchanged(self, client, catalog, routing):
        routing(FakeSearchGateway(), enabled=False)

        body = (await client.get("/api/v1/products")).json()

        assert set(body) >= {"items", "total", "page", "page_size", "pages"}
        assert body["pages"] == 1

    async def test_admin_search_is_unaffected_by_routing(self, client, catalog, routing):
        # §9.2: admin search stays lexical and independent of any provider.
        from tests.integration.conftest import auth_headers, make_admin

        gateway = routing(FakeSearchGateway(_remote([])))
        admin = await make_admin(client)

        response = await client.get(
            "/api/v1/admin/products", params={"q": "tent"}, headers=auth_headers(admin)
        )

        assert response.status_code == 200
        assert gateway.calls == []
