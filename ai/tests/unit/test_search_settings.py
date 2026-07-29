from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DatabaseSettings, Settings

BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "INTERNAL_API_KEY": "x" * 16,
    "MCP_BEARER_TOKEN": "y" * 16,
    "OLLAMA_API_KEY": "dummy",
}


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})


def test_smart_search_is_off_by_default():
    settings = make()
    assert settings.SMART_SEARCH_ENABLED is False
    # Dimensions stay unset until a benchmark picks a model.
    assert settings.EMBEDDING_DIMENSIONS is None


def test_enabling_smart_search_without_a_model_refuses_to_boot():
    with pytest.raises(ValidationError) as exc:
        make(SMART_SEARCH_ENABLED=True)
    message = str(exc.value)
    assert "EMBEDDING_PROVIDER" in message
    assert "EMBEDDING_MODEL" in message
    assert "EMBEDDING_DIMENSIONS" in message


def test_enabling_smart_search_with_a_full_model_config_is_accepted():
    settings = make(
        SMART_SEARCH_ENABLED=True,
        EMBEDDING_PROVIDER="somebody",
        EMBEDDING_MODEL="some-multilingual-model",
        EMBEDDING_DIMENSIONS=1024,
    )
    assert settings.SMART_SEARCH_ENABLED is True
    assert settings.EMBEDDING_DIMENSIONS == 1024


def test_the_search_models_are_configured_separately_from_the_chat_model():
    # Reusing OLLAMA_MODEL for embeddings would silently ship prose as vectors.
    settings = make()
    assert settings.EMBEDDING_MODEL != settings.OLLAMA_MODEL
    assert settings.EMBEDDING_MODEL == ""


def test_reranker_timeout_cannot_exceed_the_search_deadline():
    with pytest.raises(ValidationError, match="RERANKER_TIMEOUT_SECONDS"):
        make(RERANKER_TIMEOUT_SECONDS=5.0, SEARCH_DEADLINE_SECONDS=3.0)


def test_the_search_deadline_is_far_below_the_chat_timeout():
    # A shopper on a catalog page will not wait an LLM-length timeout for results.
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
    # Without a shared transaction with the web service's writes, the sweep interval is what
    # bounds how stale an edited product's document can be.
    assert make().SEARCH_INDEX_SWEEP_SECONDS <= 60


def test_the_coverage_threshold_tolerates_a_product_mid_reindex():
    # Not 1.0. At 46 products a single document being rewritten would otherwise move the whole
    # store from §12's step 3 to step 4 and back on every edit.
    settings = make()
    assert 0 < settings.SEARCH_INDEX_MIN_COVERAGE < 1.0
    assert settings.SEARCH_INDEX_MIN_COVERAGE <= 45 / 46


def test_the_backoff_cap_is_shorter_than_the_lease():
    # A backoff longer than the lease would let a job's next attempt fall outside the window
    # the lease protects, which is confusing to reason about rather than actually unsafe.
    settings = make()
    assert settings.SEARCH_INDEX_BACKOFF_CAP_SECONDS >= settings.SEARCH_INDEX_POLL_SECONDS


def test_lexical_weights_rank_the_name_above_the_facets_above_the_description():
    # These multiply the setweight labels the index worker stores. Inverting them would rank a
    # category word as highly as a product name, which is the precision risk that putting
    # category and origin into the index introduces in the first place.
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
    # CI's Schema drift step supplies DATABASE_URL and nothing else. This failed the first time
    # CI ever ran, and no local run could reproduce it because the repo-root .env fills every
    # gap on a developer machine. Asserted here so a future required setting cannot silently
    # break migrations again.
    settings = DatabaseSettings(_env_file=None, DATABASE_URL="postgresql://u:p@localhost:5432/db")

    assert settings.sqlalchemy_database_url.startswith("postgresql+asyncpg://")
