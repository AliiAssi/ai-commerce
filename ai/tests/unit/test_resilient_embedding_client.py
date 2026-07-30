from __future__ import annotations

import asyncio

import pytest

from app.application.llm.embedding_providers import EmbeddingProviders
from app.application.llm.iembedding_client import (
    ERROR_RATE_LIMITED,
    ERROR_UNAUTHORIZED,
    EmbeddingError,
)
from app.application.llm.resilient_embedding_client import ResilientEmbeddingClient
from app.core.vector_schema import FALLBACK_SLOT, PRIMARY_SLOT
from tests.unit.fakes import FakeEmbeddingClient

BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "INTERNAL_API_KEY": "x" * 16,
    "MCP_BEARER_TOKEN": "y" * 16,
    "OLLAMA_API_KEY": "dummy",
}


def settings(**overrides):
    from app.core.config import Settings

    return Settings(_env_file=None, **{**BASE, **overrides})


def wrap(inner, **overrides) -> ResilientEmbeddingClient:
    # Retries are real sleeps, so every test that exercises one sets the backoff aside by
    # patching the module constant rather than waiting a second per assertion.
    return ResilientEmbeddingClient(inner, settings(**overrides))


@pytest.fixture(autouse=True)
def _instant_backoff(monkeypatch):
    monkeypatch.setattr(
        "app.application.llm.resilient_embedding_client._BACKOFF_SECONDS", (0.0, 0.0)
    )


class TestRetry:
    async def test_a_rate_limit_is_retried_and_can_succeed(self):
        # 429 is the one failure that must not be treated as final: the free tier refused
        # part-way through the phase-5 bake-off and the run was recoverable.
        inner = FakeEmbeddingClient(
            fail_with=EmbeddingError("slow down", code=ERROR_RATE_LIMITED), fail_times=1
        )
        batch = await wrap(inner).embed_query("olive oil")

        assert len(batch.vectors) == 1
        assert len(inner.query_calls) == 2

    async def test_a_revoked_key_is_not_retried(self):
        # Retrying an unauthorized response only costs time to reach the same answer, and on a
        # 3 s deadline that time is the shopper's.
        inner = FakeEmbeddingClient(
            fail_with=EmbeddingError("nope", code=ERROR_UNAUTHORIZED), fail_times=None
        )
        with pytest.raises(EmbeddingError) as exc:
            await wrap(inner).embed_query("olive oil")

        assert exc.value.code == ERROR_UNAUTHORIZED
        assert len(inner.query_calls) == 1

    async def test_a_hang_is_bounded_by_the_embedding_timeout(self):
        # Without this the request would sit on the provider until its own socket timeout, which
        # §14.1 does not budget for.
        class Hanging(FakeEmbeddingClient):
            async def embed_query(self, text: str):
                await asyncio.sleep(10)

        with pytest.raises(EmbeddingError, match="timed out"):
            await wrap(Hanging(), EMBEDDING_TIMEOUT_SECONDS=0.01).embed_query("olive oil")


class TestCircuitBreaker:
    async def test_the_circuit_opens_after_the_configured_run_of_failures(self):
        # §12: repeated failures must stop every query waiting out the same timeout. Once open,
        # the provider is not called at all.
        inner = FakeEmbeddingClient(fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED))
        client = wrap(inner, EMBEDDING_BREAKER_FAILURES=2)

        for _ in range(2):
            with pytest.raises(EmbeddingError):
                await client.embed_query("olive oil")
        calls_before = len(inner.query_calls)

        with pytest.raises(EmbeddingError, match="circuit is open"):
            await client.embed_query("olive oil")

        assert client.is_open
        assert len(inner.query_calls) == calls_before, "an open circuit still called the provider"

    async def test_the_circuit_probes_and_closes_on_its_own(self):
        # §12 requires each circuit to probe recovery and close automatically — otherwise a
        # transient outage needs a deploy to recover from.
        inner = FakeEmbeddingClient(
            fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED), fail_times=2
        )
        client = wrap(inner, EMBEDDING_BREAKER_FAILURES=2, EMBEDDING_BREAKER_RESET_SECONDS=0.01)

        for _ in range(2):
            with pytest.raises(EmbeddingError):
                await client.embed_query("olive oil")
        assert client.is_open

        await asyncio.sleep(0.02)
        batch = await client.embed_query("olive oil")

        assert len(batch.vectors) == 1
        assert not client.is_open

    async def test_one_success_clears_the_failure_run(self):
        # Consecutive, not cumulative. A provider that fails once an hour must never accumulate
        # its way to an open circuit.
        blip = EmbeddingError("blip", code=ERROR_UNAUTHORIZED)
        inner = FakeEmbeddingClient(fail_with=blip, fail_times=1)
        client = wrap(inner, EMBEDDING_BREAKER_FAILURES=2)

        with pytest.raises(EmbeddingError):
            await client.embed_query("first")
        await client.embed_query("second")

        inner.set_failure(blip, times=1)
        with pytest.raises(EmbeddingError):
            await client.embed_query("third")

        # Two failures in total, but never two in a row, so the circuit is still closed.
        assert not client.is_open


class TestProviderSlots:
    async def test_a_query_reports_which_column_its_vector_belongs_to(self):
        # The whole reason failover is safe: retrieval compares against the column named here,
        # so the query and the documents always came from the same model.
        providers = EmbeddingProviders(primary=FakeEmbeddingClient(model="primary-model"))

        _, slot = await providers.embed_query("olive oil")

        assert slot == PRIMARY_SLOT

    async def test_a_failing_primary_falls_over_to_the_second_column(self):
        primary = FakeEmbeddingClient(
            model="primary-model", fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED)
        )
        providers = EmbeddingProviders(
            primary=primary, fallback=FakeEmbeddingClient(model="fallback-model")
        )

        batch, slot = await providers.embed_query("olive oil")

        assert slot == FALLBACK_SLOT
        assert batch.model == "fallback-model"

    async def test_a_document_batch_never_falls_over(self):
        # A document written into the primary column by the fallback's model would be invisible
        # at query time and would poison that column for every later search. The slot is named
        # by the caller and honoured exactly.
        primary = FakeEmbeddingClient(
            model="primary-model", fail_with=EmbeddingError("down", code=ERROR_UNAUTHORIZED)
        )
        fallback = FakeEmbeddingClient(model="fallback-model")
        providers = EmbeddingProviders(primary=primary, fallback=fallback)

        with pytest.raises(EmbeddingError):
            await providers.embed_documents(PRIMARY_SLOT, ["a document"])

        assert fallback.document_calls == [], "the fallback embedded into the primary's column"

    async def test_an_unconfigured_slot_is_absent_rather_than_an_error(self):
        # No fallback provider is the ordinary configuration, and asking about its column must
        # not raise — the sweep asks on every pass.
        providers = EmbeddingProviders(primary=FakeEmbeddingClient())

        assert providers.configured == (PRIMARY_SLOT,)
        assert await providers.embed_documents(FALLBACK_SLOT, ["a document"]) is None

    async def test_no_provider_at_all_reports_itself_rather_than_pretending(self):
        providers = EmbeddingProviders(primary=None)

        assert not providers.any_configured
        with pytest.raises(EmbeddingError, match="no embedding provider"):
            await providers.embed_query("olive oil")
