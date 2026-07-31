from __future__ import annotations

import httpx
import pytest

from app.application.llm.gemini_embedding_client import GeminiEmbeddingClient
from app.application.llm.iembedding_client import EmbeddingError
from app.application.llm.openai_embedding_client import OpenAICompatibleEmbeddingClient

BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "INTERNAL_API_KEY": "x" * 16,
    "MCP_BEARER_TOKEN": "y" * 16,
    "OLLAMA_API_KEY": "dummy",
}


def settings(**overrides):
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        **{
            **BASE,
            "EMBEDDING_MODEL": "some-model",
            "EMBEDDING_API_KEY": "secret-key-value",
            "EMBEDDING_DIMENSIONS": 4,
            **overrides,
        },
    )


def transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example")


def gemini_reply(vectors):
    return httpx.Response(200, json={"embeddings": [{"values": v} for v in vectors]})


def openai_reply(vectors, *, order=None):
    order = order if order is not None else range(len(vectors))
    return httpx.Response(
        200,
        json={"data": [{"index": i, "embedding": v} for i, v in zip(order, vectors, strict=True)]},
    )


class TestGemini:
    async def test_documents_and_queries_use_different_task_types(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            body = json.loads(request.content)
            seen.append(body["requests"][0]["taskType"])
            return gemini_reply([[1.0, 0.0, 0.0, 0.0]] * len(body["requests"]))

        client = GeminiEmbeddingClient(settings(), transport(handler))
        await client.embed_documents(["a", "b"])
        await client.embed_query("q")

        assert seen == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]

    async def test_the_requested_width_is_sent(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            seen.update(json.loads(request.content)["requests"][0])
            return gemini_reply([[0.0] * 4])

        await GeminiEmbeddingClient(settings(), transport(handler)).embed_query("q")

        assert seen["outputDimensionality"] == 4

    async def test_a_width_pgvector_cannot_index_is_refused_at_construction(self):
        with pytest.raises(EmbeddingError, match="HNSW"):
            GeminiEmbeddingClient(settings(EMBEDDING_DIMENSIONS=3072))

    async def test_a_provider_error_does_not_leak_its_message(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {"message": "key sk-abc123 is invalid"}})

        client = GeminiEmbeddingClient(settings(), transport(handler))
        with pytest.raises(EmbeddingError) as exc:
            await client.embed_query("q")

        assert "sk-abc123" not in str(exc.value)


class TestOpenAICompatible:
    async def test_results_are_reordered_by_index_not_by_position(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return openai_reply([[9.0] * 4, [1.0] * 4], order=[1, 0])

        client = OpenAICompatibleEmbeddingClient(settings(), transport(handler))
        batch = await client.embed_documents(["first", "second"])

        assert batch.vectors[0] == (1.0,) * 4
        assert batch.vectors[1] == (9.0,) * 4

    async def test_the_dimensions_parameter_is_sent(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            seen.update(json.loads(request.content))
            return openai_reply([[0.0] * 4])

        await OpenAICompatibleEmbeddingClient(settings(), transport(handler)).embed_query("q")

        assert seen["dimensions"] == 4
        assert seen["input"] == ["q"]


class TestBatchValidation:
    async def test_a_short_batch_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return gemini_reply([[0.0] * 4])

        client = GeminiEmbeddingClient(settings(), transport(handler))
        with pytest.raises(EmbeddingError, match="expected 3 vectors"):
            await client.embed_documents(["a", "b", "c"])

    async def test_the_wrong_width_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return gemini_reply([[0.0] * 99])

        client = GeminiEmbeddingClient(settings(), transport(handler))
        with pytest.raises(EmbeddingError, match="expected 4 dimensions"):
            await client.embed_query("q")

    async def test_ragged_widths_are_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return gemini_reply([[0.0] * 4, [0.0] * 3])

        client = GeminiEmbeddingClient(settings(), transport(handler))
        with pytest.raises(EmbeddingError, match="differing widths"):
            await client.embed_documents(["a", "b"])

    async def test_an_unrecognisable_response_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        client = GeminiEmbeddingClient(settings(), transport(handler))
        with pytest.raises(EmbeddingError, match="expected shape"):
            await client.embed_query("q")

    async def test_an_empty_input_makes_no_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an empty batch")

        client = GeminiEmbeddingClient(settings(), transport(handler))

        assert (await client.embed_documents([])).vectors == ()


class TestFailureCodes:
    @pytest.mark.parametrize(
        ("status", "code", "retryable"),
        [
            (429, "rate_limited", True),
            (503, "provider_unavailable", True),
            (401, "unauthorized", False),
            (403, "unauthorized", False),
            (400, "bad_request", False),
        ],
    )
    async def test_a_status_becomes_a_code(self, status, code, retryable):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": {"message": "key sk-abc123 leaked"}})

        client = GeminiEmbeddingClient(settings(), transport(handler))
        with pytest.raises(EmbeddingError) as exc:
            await client.embed_query("q")

        assert exc.value.code == code
        assert exc.value.retryable is retryable
        assert "sk-abc123" not in str(exc.value)

    async def test_a_malformed_body_is_not_retryable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        client = OpenAICompatibleEmbeddingClient(settings(), transport(handler))
        with pytest.raises(EmbeddingError) as exc:
            await client.embed_query("q")

        assert exc.value.code == "malformed_response"
        assert exc.value.retryable is False
