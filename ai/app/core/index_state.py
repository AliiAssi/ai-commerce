from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IndexCoverage:
    """Whether retrieval may read the document table, settled outside the request path.

    §12's ladder has two lexical rungs: step 3 over this service's `ai_search_documents`, step 4
    over web's `products.search_vector`. Which one runs depends on index coverage, and checking
    that per request would put two counts on the hot path forever. So it is one mutable
    process-wide instance instead — probed at boot and refreshed by every sweep, exactly like
    `SearchCapabilities`. Staleness is bounded by the sweep interval, which is already the bound
    on index freshness itself.

    It defaults to *not* ready, which is the opposite of `SearchCapabilities.trigram`, and the
    difference is deliberate. An unreachable database leaves trigram assumed present because the
    lexical leg still answers without it; here the fallback direction is `products.search_vector`,
    which is a generated column that is always populated and can never be empty. Unknown must
    therefore mean step 4: step 3 over an unfilled table returns nothing at all.
    """

    ready: bool = False
    active_products: int = 0
    documents: int = 0

    def update(self, *, active_products: int, documents: int, threshold: float) -> None:
        self.active_products = active_products
        self.documents = documents
        # An empty catalog is reported as not ready. There is nothing to find either way, but it
        # keeps "ready" meaning "there is positive evidence the index is populated" rather than
        # "nothing has contradicted it yet" — which is what makes a stale value safe.
        self.ready = active_products > 0 and documents / active_products >= threshold
