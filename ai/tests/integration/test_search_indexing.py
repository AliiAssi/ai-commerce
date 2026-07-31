from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Text, cast, func, select, update

from app.application.dtos.index_dto import ERROR_DATABASE
from app.application.dtos.search_dto import RetrievalRequest
from app.application.iservices.iindex_service import IIndexService
from app.application.search.document import DOCUMENT_VERSION, build_document_text, document_hash
from app.application.search.parser import IntentParser, resolve_filters
from app.core.container import container, open_scope
from app.core.index_state import IndexCoverage
from app.core.search_aliases import AliasLibrary
from app.infrastructure.database.store_tables import categories, products
from app.infrastructure.irepositories.isearch_index_repository import ISearchIndexRepository
from app.infrastructure.irepositories.isearch_repository import ISearchRepository
from app.infrastructure.models.search import SearchDocument, SearchIndexJob

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

documents = SearchDocument.__table__
jobs = SearchIndexJob.__table__


@pytest.fixture
def index_service(app) -> IIndexService:
    return container.resolve(IIndexService)


@pytest.fixture
def coverage(app) -> IndexCoverage:
    return container.resolve(IndexCoverage)


@pytest.fixture
async def retrieve(app):

    async def run(query: str):
        aliases = container.resolve(AliasLibrary)
        intent = IntentParser(aliases).parse(query)
        filters = resolve_filters(intent, aliases)
        async with open_scope() as scope:
            return await scope.resolve(ISearchRepository).retrieve(
                RetrievalRequest(
                    semantic_text=intent.semantic_text,
                    normalized_query=intent.normalized_query,
                    filters=filters,
                )
            )

    return run


async def _scalar(stmt):
    async with container.session_factory() as session, session.begin():
        return await session.scalar(stmt)


async def _all(stmt):
    async with container.session_factory() as session, session.begin():
        return (await session.execute(stmt)).all()


async def _execute(stmt, params=None):
    async with container.session_factory() as session, session.begin():
        return await session.execute(stmt, params) if params else await session.execute(stmt)


async def _index_everything(service: IIndexService) -> None:
    await service.sweep()
    await service.drain(max_batches=50)
    await service.refresh_coverage()


class TestDocumentGeneration:
    async def test_the_sql_hash_agrees_with_the_python_hash_for_every_product(
        self, index_service, beit_catalog
    ):
        from app.infrastructure.repositories.search_index_repository import _document_hash_sql

        rows = await _all(
            select(
                products.c.id,
                products.c.name,
                categories.c.name.label("category_name"),
                products.c.origin,
                products.c.description,
                _document_hash_sql().label("sql_hash"),
            ).select_from(products.join(categories, categories.c.id == products.c.category_id))
        )
        assert len(rows) == len(beit_catalog)
        for row in rows:
            expected = document_hash(
                build_document_text(
                    name=row.name,
                    category_name=row.category_name,
                    origin=row.origin,
                    description=row.description,
                )
            )
            assert row.sql_hash == expected, f"hash disagrees for product {row.id}"

    async def test_a_product_without_an_origin_omits_the_origin_line_on_both_sides(
        self, index_service, catalog
    ):
        from app.infrastructure.repositories.search_index_repository import _document_hash_sql

        rows = await _all(
            select(
                products.c.name,
                categories.c.name.label("category_name"),
                products.c.description,
                _document_hash_sql().label("sql_hash"),
            ).select_from(products.join(categories, categories.c.id == products.c.category_id))
        )
        for row in rows:
            text_value = build_document_text(
                name=row.name,
                category_name=row.category_name,
                origin=None,
                description=row.description,
            )
            assert "Origin:" not in text_value
            assert row.sql_hash == document_hash(text_value)

    async def test_a_stored_document_carries_the_format_and_its_version(
        self, index_service, beit_catalog
    ):
        await _index_everything(index_service)

        row = (
            await _all(
                select(documents.c.document_text, documents.c.document_version)
                .join(products, products.c.id == documents.c.product_id)
                .where(products.c.name == "Baladi Extra Virgin Olive Oil")
            )
        )[0]
        assert row.document_version == DOCUMENT_VERSION
        lines = row.document_text.split("\n")
        assert lines[0] == "Name: Baladi Extra Virgin Olive Oil"
        assert lines[1] == "Category: Olive Oil & Za'atar"
        assert lines[2] == "Origin: Koura, North Lebanon"
        assert lines[3].startswith("Description: ")

    async def test_the_stored_vectors_weight_the_name_above_the_description(
        self, index_service, beit_catalog
    ):
        await _index_everything(index_service)

        vector = await _scalar(
            select(cast(documents.c.search_vector_en, Text))
            .join(products, products.c.id == documents.c.product_id)
            .where(products.c.name == "Baladi Extra Virgin Olive Oil")
        )
        assert "'baladi':1A" in vector
        assert re.search(r"'koura':\d+B", vector)
        described = re.search(r"'bitter':(\d+)([A-D]?)", vector)
        assert described is not None and described.group(2) == ""


class TestDriftSweep:
    async def test_a_fresh_catalog_enqueues_every_active_product(self, index_service, beit_catalog):
        report = await index_service.sweep()

        assert report.enqueued == len(beit_catalog)
        assert await _scalar(select(func.count()).select_from(jobs)) == len(beit_catalog)

    async def test_indexing_clears_the_queue_and_a_second_sweep_finds_no_drift(
        self, index_service, beit_catalog
    ):
        await index_service.sweep()
        report = await index_service.drain(max_batches=50)

        assert report.indexed == len(beit_catalog)
        assert await _scalar(select(func.count()).select_from(jobs)) == 0
        assert await _scalar(select(func.count()).select_from(documents)) == len(beit_catalog)

        second = await index_service.sweep()
        assert second.enqueued == 0

    @pytest.mark.parametrize(
        ("column", "value"),
        [
            ("name", "Renamed Baladi Olive Oil"),
            ("description", "A completely different description."),
            ("origin", "Batroun"),
        ],
    )
    async def test_editing_a_semantic_field_re_enqueues_the_product(
        self, index_service, beit_catalog, column, value
    ):
        await _index_everything(index_service)
        await _execute(
            update(products)
            .where(products.c.name == "Baladi Extra Virgin Olive Oil")
            .values(**{column: value})
        )

        report = await index_service.sweep()
        assert report.enqueued == 1

    async def test_recategorising_a_product_re_enqueues_it(self, index_service, beit_catalog):
        await _index_everything(index_service)
        other = await _scalar(select(categories.c.id).where(categories.c.slug == "pantry"))
        await _execute(
            update(products)
            .where(products.c.name == "Baladi Extra Virgin Olive Oil")
            .values(category_id=other)
        )

        report = await index_service.sweep()
        assert report.enqueued == 1

    @pytest.mark.parametrize(
        ("column", "value"),
        [("price", 99), ("stock", 0), ("rating_avg", 1), ("review_count", 999)],
    )
    async def test_editing_a_live_field_does_not_re_enqueue_anything(
        self, index_service, beit_catalog, column, value
    ):
        await _index_everything(index_service)
        await _execute(
            update(products)
            .where(products.c.name == "Baladi Extra Virgin Olive Oil")
            .values(**{column: value})
        )

        report = await index_service.sweep()
        assert report.enqueued == 0

    async def test_a_document_version_bump_re_enqueues_the_whole_catalog(
        self, index_service, beit_catalog
    ):
        await _index_everything(index_service)
        await _execute(update(documents).values(document_version=DOCUMENT_VERSION - 1))

        report = await index_service.sweep()
        assert report.enqueued == len(beit_catalog)


class TestArchival:
    async def test_archiving_prunes_the_document_and_unarchiving_restores_it(
        self, index_service, beit_catalog, archive_product
    ):
        await _index_everything(index_service)
        await archive_product("Baladi Extra Virgin Olive Oil")

        report = await index_service.sweep()
        assert report.pruned == 1
        assert await _scalar(select(func.count()).select_from(documents)) == len(beit_catalog) - 1

        await _execute(
            update(products)
            .where(products.c.name == "Baladi Extra Virgin Olive Oil")
            .values(is_archived=False)
        )
        restored = await index_service.sweep()
        assert restored.enqueued == 1
        await index_service.drain(max_batches=50)
        assert await _scalar(select(func.count()).select_from(documents)) == len(beit_catalog)

    async def test_a_deleted_product_leaves_no_document_behind(self, index_service, beit_catalog):
        await _index_everything(index_service)
        await _execute(products.delete().where(products.c.name == "Baladi Extra Virgin Olive Oil"))

        assert await _scalar(select(func.count()).select_from(documents)) == len(beit_catalog) - 1
        report = await index_service.sweep()
        assert report.enqueued == 0


class TestClaimProtocol:
    async def test_two_workers_never_claim_the_same_job(self, index_service, beit_catalog):
        await index_service.sweep()

        async with (
            container.session_factory() as first,
            first.begin(),
            container.session_factory() as second,
            second.begin(),
        ):
            claimed_a = await _repository(first).claim_batch(
                worker_id="a", size=5, lease_seconds=60, max_attempts=5
            )
            claimed_b = await _repository(second).claim_batch(
                worker_id="b", size=5, lease_seconds=60, max_attempts=5
            )

        ids_a = {job.product_id for job in claimed_a}
        ids_b = {job.product_id for job in claimed_b}
        assert len(ids_a) == 5 and len(ids_b) == 5
        assert not ids_a & ids_b

    async def test_a_leased_job_is_invisible_until_its_lease_expires(
        self, index_service, beit_catalog
    ):
        await index_service.sweep()
        async with container.session_factory() as session, session.begin():
            claimed = await _repository(session).claim_batch(
                worker_id="holder", size=1, lease_seconds=600, max_attempts=5
            )
        held = claimed[0].product_id

        async with container.session_factory() as session, session.begin():
            others = await _repository(session).claim_batch(
                worker_id="other", size=100, lease_seconds=60, max_attempts=5
            )
        assert held not in {job.product_id for job in others}

        await _execute(
            update(jobs)
            .where(jobs.c.product_id == held)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        async with container.session_factory() as session, session.begin():
            reclaimed = await _repository(session).claim_batch(
                worker_id="other", size=100, lease_seconds=60, max_attempts=5
            )
        assert held in {job.product_id for job in reclaimed}

    async def test_an_abandoned_batch_is_reindexed_without_loss_or_duplication(
        self, index_service, beit_catalog
    ):
        await index_service.sweep()
        async with container.session_factory() as session, session.begin():
            abandoned = await _repository(session).claim_batch(
                worker_id="crashed", size=8, lease_seconds=600, max_attempts=5
            )
        assert len(abandoned) == 8

        await index_service.drain(max_batches=50)
        assert await _scalar(select(func.count()).select_from(documents)) == len(beit_catalog) - 8

        await _execute(
            update(jobs)
            .where(jobs.c.worker_id == "crashed")
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await index_service.drain(max_batches=50)

        assert await _scalar(select(func.count()).select_from(documents)) == len(beit_catalog)
        assert await _scalar(select(func.count()).select_from(jobs)) == 0
        assert (await index_service.sweep()).enqueued == 0

    async def test_shutdown_hands_back_this_process_leases(self, index_service, beit_catalog):
        await index_service.sweep()
        async with container.session_factory() as session, session.begin():
            await _repository(session).claim_batch(
                worker_id=index_service.worker_id, size=4, lease_seconds=600, max_attempts=5
            )

        assert await index_service.release_leases() == 4
        assert (
            await _scalar(
                select(func.count()).select_from(jobs).where(jobs.c.lease_until.is_not(None))
            )
            == 0
        )


class TestFailureHandling:
    async def test_a_failure_backs_the_job_off_and_records_a_code_not_a_message(
        self, index_service, beit_catalog
    ):
        await index_service.sweep()
        product_id = await _scalar(select(products.c.id).limit(1))
        async with container.session_factory() as session, session.begin():
            await _repository(session).fail(product_id, error_code=ERROR_DATABASE, delay_seconds=30)

        row = (
            await _all(
                select(jobs.c.attempts, jobs.c.last_error_code, jobs.c.next_attempt_at).where(
                    jobs.c.product_id == product_id
                )
            )
        )[0]
        assert row.attempts == 1
        assert row.last_error_code == ERROR_DATABASE
        assert row.next_attempt_at > datetime.now(UTC) + timedelta(seconds=20)

    async def test_the_backoff_is_exponential_and_capped(self, index_service):
        delays = [index_service.backoff_seconds(n) for n in range(0, 12)]
        assert delays[0] < delays[1] < delays[2]
        assert delays[1] == delays[0] * 2
        assert max(delays) <= 300.0
        assert delays[-1] == 300.0

    async def test_an_exhausted_job_stops_being_claimed_and_the_sweep_leaves_it_alone(
        self, index_service, beit_catalog
    ):
        await index_service.sweep()
        product_id = await _scalar(select(products.c.id).limit(1))
        await _execute(
            update(jobs)
            .where(jobs.c.product_id == product_id)
            .values(attempts=5, last_error_code=ERROR_DATABASE)
        )

        await index_service.drain(max_batches=50)
        assert (
            await _scalar(
                select(func.count()).select_from(jobs).where(jobs.c.product_id == product_id)
            )
            == 1
        )

        await index_service.sweep()
        row = (await _all(select(jobs.c.attempts).where(jobs.c.product_id == product_id)))[0]
        assert row.attempts == 5

        failed = await index_service.failed_jobs()
        assert [job.product_id for job in failed] == [product_id]

    async def test_an_operator_reset_makes_an_exhausted_job_claimable_again(
        self, index_service, beit_catalog
    ):
        await index_service.sweep()
        product_id = await _scalar(select(products.c.id).limit(1))
        await _execute(
            update(jobs)
            .where(jobs.c.product_id == product_id)
            .values(attempts=5, last_error_code=ERROR_DATABASE)
        )

        await index_service.enqueue([product_id], reset=True)
        await index_service.drain(max_batches=50)

        assert (
            await _scalar(
                select(func.count()).select_from(jobs).where(jobs.c.product_id == product_id)
            )
            == 0
        )
        assert await index_service.failed_jobs() == []


class TestCoverageGate:
    async def test_an_unfilled_index_leaves_retrieval_on_the_catalog_vector(
        self, index_service, beit_catalog, retrieve
    ):
        await index_service.refresh_coverage()

        result = await retrieve("olive oil")
        assert result.documents_used is False
        assert result.total > 0

    async def test_a_filled_index_moves_retrieval_onto_the_documents(
        self, index_service, coverage, beit_catalog, retrieve
    ):
        await _index_everything(index_service)

        assert coverage.ready is True
        result = await retrieve("olive oil")
        assert result.documents_used is True
        assert result.total > 0

    async def test_coverage_below_the_threshold_falls_back(
        self, index_service, coverage, beit_catalog, retrieve
    ):
        await _index_everything(index_service)
        assert coverage.ready is True

        await _execute(
            documents.delete().where(documents.c.product_id.in_(select(products.c.id).limit(10)))
        )
        await index_service.refresh_coverage()

        assert coverage.ready is False
        assert (await retrieve("olive oil")).documents_used is False

    async def test_a_category_word_is_findable_only_through_the_documents(
        self, index_service, beit_catalog, retrieve
    ):
        before = await retrieve("tableware")
        assert before.documents_used is False
        assert before.lexical_hits == 0

        await _index_everything(index_service)

        after = await retrieve("tableware")
        assert after.documents_used is True
        assert after.lexical_hits > 0
        assert after.total > before.total

    async def test_an_origin_is_findable_through_the_lexical_leg(
        self, index_service, beit_catalog, retrieve
    ):
        await _index_everything(index_service)

        result = await retrieve("chouf")
        assert result.documents_used is True
        assert result.lexical_hits > 0

    async def test_the_product_name_still_outranks_a_category_match(
        self, index_service, beit_catalog, retrieve
    ):
        await _index_everything(index_service)

        result = await retrieve("coffee")
        assert result.documents_used is True
        top = await _scalar(select(products.c.name).where(products.c.id == result.product_ids[0]))
        assert "Coffee" in top


class TestCoverageReporting:
    async def test_coverage_counts_only_active_products(
        self, index_service, coverage, beit_catalog, archive_product
    ):
        await _index_everything(index_service)
        await archive_product("Baladi Extra Virgin Olive Oil")

        reported = await index_service.refresh_coverage()
        assert reported.active_products == len(beit_catalog) - 1
        assert reported.documents == len(beit_catalog) - 1

    async def test_an_empty_catalog_is_reported_as_not_ready(self, index_service, coverage):
        reported = await index_service.refresh_coverage()

        assert reported.active_products == 0
        assert coverage.ready is False


def _repository(session) -> ISearchIndexRepository:
    from app.infrastructure.repositories.search_index_repository import SearchIndexRepository

    return SearchIndexRepository(session)
