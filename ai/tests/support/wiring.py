from __future__ import annotations

from app.core.container import Container
from tests.support.irelevance_service import IRelevanceService
from tests.support.relevance import RelevanceCorpus, load_corpus_or_exit
from tests.support.relevance_service import RelevanceService


def configure_relevance(container: Container) -> None:
    container.bind_instance(RelevanceCorpus, load_corpus_or_exit())
    container.bind(IRelevanceService, RelevanceService, singleton=True)
