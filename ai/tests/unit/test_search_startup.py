from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy.exc import OperationalError

from app import main
from app.application.dtos.search_dto import CatalogLexiconDTO
from app.core.search_aliases import AliasError, AliasLibrary, load_aliases
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from tests.unit.conftest import FakeScope

GOOD = CatalogLexiconDTO(
    category_slugs=[
        "olive-oil",
        "pantry",
        "coffee-sweets",
        "ceramics",
        "soap-skincare",
        "textiles",
        "woodwork",
        "glass-copper",
    ],
    origins=[
        "Akkar",
        "Baalbek",
        "Bcharre, North Lebanon",
        "Beirut",
        "Beit Chabab",
        "Bekaa Valley",
        "Chouf",
        "Deir el Qamar",
        "Hasbaya, South Lebanon",
        "Hermel",
        "Jabal Moussa",
        "Jezzine, South Lebanon",
        "Koura, North Lebanon",
        "Rachaya",
        "Sarafand, South Lebanon",
        "Tripoli",
        "Tripoli, North Lebanon",
        "Tyre, South Lebanon",
        "Zgharta, North Lebanon",
        "Zouk Mikael",
    ],
)

STALE = CatalogLexiconDTO(category_slugs=["something-else"], origins=["Batroun"])


class _Settings:
    def __init__(self, enabled: bool) -> None:
        self.SMART_SEARCH_ENABLED = enabled


class _Repo(ISearchRepository):
    def __init__(self, terms: CatalogLexiconDTO | Exception) -> None:
        self._terms = terms

    async def retrieve(self, request):  # pragma: no cover - not exercised here
        raise NotImplementedError

    async def rerank_candidates(self, product_ids):  # pragma: no cover - not exercised here
        raise NotImplementedError

    async def detect_capabilities(self):  # pragma: no cover - not exercised here
        raise NotImplementedError

    async def cached_query_vector(self, cache_key):  # pragma: no cover - not exercised here
        raise NotImplementedError

    async def store_query_vector(self, cache_key, vector, *, language, ttl_seconds):
        raise NotImplementedError  # pragma: no cover - not exercised here

    async def catalog_terms(self) -> CatalogLexiconDTO:
        if isinstance(self._terms, Exception):
            raise self._terms
        return self._terms


@pytest.fixture
def wire(monkeypatch):

    def apply(terms):
        @asynccontextmanager
        async def fake_scope():
            yield FakeScope({ISearchRepository: _Repo(terms)})

        monkeypatch.setattr(main, "open_scope", fake_scope)
        aliases = load_aliases()
        monkeypatch.setattr(
            main.container,
            "resolve",
            lambda interface: aliases if interface is AliasLibrary else None,
        )

    return apply


class TestVerifySearchLexicon:
    async def test_a_matching_catalog_passes(self, wire):
        wire(GOOD)

        await main.verify_search_lexicon(_Settings(enabled=True))

    async def test_a_stale_lexicon_is_fatal_when_the_feature_is_live(self, wire):
        wire(STALE)

        with pytest.raises(AliasError):
            await main.verify_search_lexicon(_Settings(enabled=True))

    async def test_a_stale_lexicon_only_logs_when_the_feature_is_off(self, wire, caplog):
        wire(STALE)

        await main.verify_search_lexicon(_Settings(enabled=False))

        assert "stale" in caplog.text

    async def test_an_unreachable_database_is_never_fatal(self, wire):
        wire(OperationalError("SELECT 1", {}, Exception("no route to host")))

        await main.verify_search_lexicon(_Settings(enabled=True))

    async def test_an_empty_catalog_is_not_treated_as_a_mismatch(self, wire):
        wire(CatalogLexiconDTO(category_slugs=[], origins=[]))

        await main.verify_search_lexicon(_Settings(enabled=True))
