from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DatabaseSettings, Settings

# Pinned rather than left to the ambient environment: pydantic reads os.environ even with
# _env_file=None, and the integration conftest exports AI_SERVICE_URL for the whole session.
BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "JWT_SECRET": "x" * 32,
    "AI_SERVICE_URL": "",
}


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})


def test_search_routing_is_off_by_default():
    assert make().SMART_SEARCH_ROUTING_ENABLED is False


def test_routing_search_without_somewhere_to_route_it_refuses_to_boot():
    # Otherwise the failure surfaces per-request instead of at startup.
    with pytest.raises(ValidationError, match="AI_SERVICE_URL"):
        make(SMART_SEARCH_ROUTING_ENABLED=True)


def test_routing_search_with_an_ai_service_is_accepted():
    settings = make(SMART_SEARCH_ROUTING_ENABLED=True, AI_SERVICE_URL="http://ai.test")
    assert settings.SMART_SEARCH_ROUTING_ENABLED is True


def test_search_timeout_must_be_positive():
    with pytest.raises(ValidationError, match="SEARCH_TIMEOUT_SECONDS"):
        make(SEARCH_TIMEOUT_SECONDS=0)


def test_search_timeout_is_far_below_the_chat_timeout():
    # A shopper on a catalog page will not wait an LLM-length timeout for results.
    #
    # Raised from 5.0 on 2026-07-31 with the owner, when RERANKER_TIMEOUT_SECONDS went to 5 s to
    # accommodate a slow cross-encoder. The bound has to clear what the AI service may spend —
    # query embedding plus retrieval plus the reranker — or the gateway abandons the request
    # before the reranker answers and web serves lexical results, which is the outcome this
    # whole chain exists to avoid. It is still a small fraction of a chat timeout, which is the
    # comparison this test is named for.
    assert make().SEARCH_TIMEOUT_SECONDS <= 10.0


def test_migrations_need_only_a_database_url():
    # CI's Schema drift step supplies DATABASE_URL and nothing else. This failed the first time
    # CI ever ran, and no local run could reproduce it because the repo-root .env fills every
    # gap on a developer machine. Asserted here so a future required setting cannot silently
    # break migrations again.
    settings = DatabaseSettings(_env_file=None, DATABASE_URL="postgresql://u:p@localhost:5432/db")

    assert settings.sqlalchemy_database_url.startswith("postgresql+asyncpg://")
