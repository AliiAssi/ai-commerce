from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DatabaseSettings, Settings
from app.core.vector_schema import EMBEDDING_VECTOR_DIMENSIONS

BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "INTERNAL_API_KEY": "x" * 16,
    "MCP_BEARER_TOKEN": "y" * 16,
    "OLLAMA_API_KEY": "dummy",
}


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})


def enabled(**overrides) -> Settings:
    return make(
        **{
            "SMART_SEARCH_ENABLED": True,
            "EMBEDDING_PROVIDER": "gemini",
            "EMBEDDING_MODEL": "gemini-embedding-001",
            "EMBEDDING_DIMENSIONS": EMBEDDING_VECTOR_DIMENSIONS,
            "EMBEDDING_API_KEY": "a-key",
            **overrides,
        }
    )


def test_smart_search_is_off_by_default():
    settings = make()
    assert settings.SMART_SEARCH_ENABLED is False
    assert settings.EMBEDDING_DIMENSIONS is None


def test_enabling_smart_search_without_a_model_refuses_to_boot():
    with pytest.raises(ValidationError) as exc:
        make(SMART_SEARCH_ENABLED=True)
    message = str(exc.value)
    assert "EMBEDDING_PROVIDER" in message
    assert "EMBEDDING_MODEL" in message
    assert "EMBEDDING_DIMENSIONS" in message


def test_enabling_smart_search_with_a_full_model_config_is_accepted():
    settings = enabled()
    assert settings.SMART_SEARCH_ENABLED is True
    assert settings.EMBEDDING_DIMENSIONS == EMBEDDING_VECTOR_DIMENSIONS


def test_enabling_smart_search_without_a_key_refuses_to_boot():
    with pytest.raises(ValidationError, match="EMBEDDING_API_KEY"):
        enabled(EMBEDDING_API_KEY="")


@pytest.mark.parametrize("width", [384, 1536])
def test_a_width_the_schema_was_not_migrated_with_refuses_to_boot(width: int):
    with pytest.raises(ValidationError, match="EMBEDDING_DIMENSIONS"):
        enabled(EMBEDDING_DIMENSIONS=width)


def test_a_half_configured_fallback_provider_refuses_to_boot():
    with pytest.raises(ValidationError, match="EMBEDDING_FALLBACK"):
        enabled(EMBEDDING_FALLBACK_PROVIDER="openrouter")


def test_a_fully_configured_fallback_provider_is_accepted():
    settings = enabled(
        EMBEDDING_FALLBACK_PROVIDER="openrouter",
        EMBEDDING_FALLBACK_MODEL="openai/text-embedding-3-large",
        EMBEDDING_FALLBACK_API_KEY="another-key",
    )
    assert settings.EMBEDDING_FALLBACK_MODEL == "openai/text-embedding-3-large"


def test_the_semantic_floor_starts_uncalibrated():
    settings = make()
    assert settings.SEARCH_SEMANTIC_MIN_SIMILARITY >= 0.0


def test_the_search_models_are_configured_separately_from_the_chat_model():
    settings = make()
    assert settings.EMBEDDING_MODEL != settings.OLLAMA_MODEL
    assert settings.EMBEDDING_MODEL == ""


def test_reranker_timeout_cannot_exceed_the_search_deadline():
    with pytest.raises(ValidationError, match="RERANKER_TIMEOUT_SECONDS"):
        make(RERANKER_TIMEOUT_SECONDS=5.0, SEARCH_DEADLINE_SECONDS=3.0)


def test_the_search_deadline_is_far_below_the_chat_timeout():
    settings = make()
    assert settings.SEARCH_DEADLINE_SECONDS < settings.LLM_TIMEOUT_SECONDS


def test_query_text_is_never_retained_longer_than_the_metrics():
    with pytest.raises(ValidationError, match="SEARCH_EVENT_QUERY_RETENTION_DAYS"):
        make(SEARCH_EVENT_QUERY_RETENTION_DAYS=400, SEARCH_EVENT_METRIC_RETENTION_DAYS=365)


@pytest.mark.parametrize("top_k", [19, 51])
def test_reranker_window_is_held_to_its_tested_range(top_k: int):
    with pytest.raises(ValidationError, match="RERANKER_TOP_K"):
        make(RERANKER_TOP_K=top_k)


@pytest.mark.parametrize("top_k", [20, 30, 50])
def test_reranker_window_accepts_its_tested_range(top_k: int):
    assert top_k == make(RERANKER_TOP_K=top_k).RERANKER_TOP_K


def test_the_index_sweep_keeps_freshness_inside_a_minute():
    assert make().SEARCH_INDEX_SWEEP_SECONDS <= 60


def test_the_coverage_threshold_tolerates_a_product_mid_reindex():
    settings = make()
    assert 0 < settings.SEARCH_INDEX_MIN_COVERAGE < 1.0
    assert settings.SEARCH_INDEX_MIN_COVERAGE <= 45 / 46


def test_the_backoff_cap_is_shorter_than_the_lease():
    settings = make()
    assert settings.SEARCH_INDEX_BACKOFF_CAP_SECONDS >= settings.SEARCH_INDEX_POLL_SECONDS


def test_lexical_weights_rank_the_name_above_the_facets_above_the_description():
    settings = make()
    assert (
        settings.SEARCH_LEXICAL_WEIGHT_NAME
        > settings.SEARCH_LEXICAL_WEIGHT_FACET
        > settings.SEARCH_LEXICAL_WEIGHT_DESCRIPTION
    )


@pytest.mark.parametrize("weight", [-0.1, 1.1])
def test_lexical_weights_are_held_to_the_range_ts_rank_accepts(weight: float):
    with pytest.raises(ValidationError, match="SEARCH_LEXICAL_WEIGHT_NAME"):
        make(SEARCH_LEXICAL_WEIGHT_NAME=weight)


def test_migrations_need_only_a_database_url():
    settings = DatabaseSettings(_env_file=None, DATABASE_URL="postgresql://u:p@localhost:5432/db")

    assert settings.sqlalchemy_database_url.startswith("postgresql+asyncpg://")
