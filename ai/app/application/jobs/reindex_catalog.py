from __future__ import annotations

import argparse
import asyncio
import sys

from app.application.iservices.iindex_service import IIndexService
from app.core.config import load_settings_or_exit
from app.core.container import container
from app.core.logging import setup_logging
from app.core.registry import configure

# A drain of a 10,000-product catalog at the default batch size is well under this; it exists so
# a bug that stopped jobs being completed ends the command instead of spinning inside it.
_MAX_BATCHES = 5_000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reindex_catalog",
        description="Bring ai_search_documents back into agreement with the catalog (§11).",
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--product-id",
        type=int,
        action="append",
        dest="product_ids",
        metavar="ID",
        help="reindex specific products; repeatable. Resets an exhausted job's attempts.",
    )
    selector.add_argument(
        "--all", action="store_true", help="rebuild every non-archived product's document"
    )
    selector.add_argument(
        "--stale-only",
        action="store_true",
        help="enqueue only hash/version drift (the default when no selector is given)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would be enqueued and write nothing"
    )
    return parser


async def _enqueue(service: IIndexService, args: argparse.Namespace) -> int:
    if args.product_ids:
        # An operator naming a product is explicitly asking for a retry, so this resets attempts
        # where the sweep deliberately does not — the sweep would otherwise turn a permanently
        # failing product into a loop no attempt cap could stop.
        return await service.enqueue(args.product_ids, reset=True)
    if args.all:
        return await service.enqueue_all_active(reset=True)
    return await service.enqueue(await service.drifted_product_ids(), reset=False)


async def _dry_run(service: IIndexService, args: argparse.Namespace) -> None:
    if args.product_ids:
        targets = list(args.product_ids)
        label = "named"
    elif args.all:
        targets = await service.active_product_ids()
        label = "active"
    else:
        targets = await service.drifted_product_ids()
        label = "drifted"
    print(f"--dry-run: {len(targets)} {label} product(s) would be enqueued")
    if targets:
        preview = ", ".join(str(pid) for pid in targets[:20])
        print(f"  ids: {preview}{' ...' if len(targets) > 20 else ''}")


async def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    settings = load_settings_or_exit()
    setup_logging(settings.ENVIRONMENT)
    configure(container, settings)
    assert container.engine is not None
    service = container.resolve(IIndexService)

    try:
        if args.dry_run:
            await _dry_run(service, args)
            return 0

        enqueued = await _enqueue(service, args)
        print(f"enqueued:   {enqueued}")

        report = await service.drain(max_batches=_MAX_BATCHES)
        coverage = await service.refresh_coverage()
        failed = await service.failed_jobs()
        pending = await service.pending_count()

        print(f"indexed:    {report.indexed}")
        print(f"failed:     {report.failed} (this run)")
        print(f"pending:    {pending} job(s) left in the queue")
        print(f"coverage:   {coverage.documents}/{coverage.active_products} active products")
        for job in failed:
            # §11 wants permanent failures reported, and §10.3 wants them reported as codes.
            print(
                f"  permanent failure: product {job.product_id} "
                f"after {job.attempts} attempt(s): {job.last_error_code}"
            )
        # A non-zero exit so a deploy step or cron wrapper notices, without hiding the report.
        return 1 if failed else 0
    finally:
        await container.engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
