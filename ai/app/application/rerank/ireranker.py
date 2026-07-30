from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.application.dtos.search_dto import SearchIntent

# Rerank outcomes, recorded on the search event (§14.5) and used to pick §9.2's mode.
#
# `skipped` and `unavailable` are deliberately different values. Skipping is correct behaviour —
# §7.3 skips reranking for explicit sorts because those sorts own the ordering — while
# unavailable is a failure that §12 requires to be reported as `degraded` with
# `reranker_unavailable`. Collapsing them would make an outage indistinguishable from a shopper
# choosing "price: low to high".
RERANK_APPLIED = "applied"
RERANK_SKIPPED = "skipped"
RERANK_UNAVAILABLE = "unavailable"


class RerankResult:
    """The order to use, and what actually happened to produce it."""

    __slots__ = ("outcome", "product_ids", "version")

    def __init__(self, product_ids: Sequence[int], *, outcome: str, version: str = "") -> None:
        self.product_ids = list(product_ids)
        self.outcome = outcome
        self.version = version

    @property
    def applied(self) -> bool:
        return self.outcome == RERANK_APPLIED


class IReranker(ABC):
    @property
    @abstractmethod
    def version(self) -> str:
        """Prompt/schema version, logged with search analytics (§7.4)."""

    @abstractmethod
    async def rerank(
        self, intent: SearchIntent, product_ids: Sequence[int], *, window: int
    ) -> RerankResult:
        """Reorder the top `window` candidates against the shopper's intent.

        Receives ids and intent only. §7.3 lists what the reranker may see and customer identity,
        history, cart and order data are all absent from it.
        """


class PassthroughReranker(IReranker):
    """Returns the RRF order untouched — §12's step 2, as the default until phase 7.

    Reported as `skipped` rather than `unavailable`, and the difference reaches the shopper.
    Nothing failed here: no reranker is configured, which is a deployment state, and
    `reranker_unavailable` would set `degraded` on every search for the whole of this phase.
    The frontend shows a "the smarter search is briefly unavailable" banner for every degraded
    reason except `feature_disabled` (`isFaultDegradation`), so reporting a fault here would put
    a permanent apology under a search that is working exactly as configured. `reranked: false`
    in the response already says the true thing.
    """

    @property
    def version(self) -> str:
        return "passthrough-1"

    async def rerank(
        self, intent: SearchIntent, product_ids: Sequence[int], *, window: int
    ) -> RerankResult:
        return RerankResult(product_ids, outcome=RERANK_SKIPPED, version=self.version)
