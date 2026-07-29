from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

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
    assert make().SEARCH_TIMEOUT_SECONDS <= 5.0
