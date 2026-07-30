from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IndexCoverage:
    """Whether retrieval may read the document table and the vector columns, settled outside the
    request path.

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

    **`ready` and `semantic` are separate on purpose.** They answer different questions — "do
    documents exist" and "do current vectors exist" — and a single flag would either switch the
    lexical leg off because an embedding provider was down, or run the semantic leg over a
    half-filled column. §12 lists "index coverage below the safe release threshold" as its own
    fallback trigger for exactly the second case. Both are computed from one scan, so they can
    never describe different moments.
    """

    ready: bool = False
    active_products: int = 0
    documents: int = 0
    # slot -> products whose stored vector matches the configured model and dimensions.
    embedded: dict[str, int] = field(default_factory=dict)
    _semantic_ready: set[str] = field(default_factory=set)

    def update(
        self,
        *,
        active_products: int,
        documents: int,
        threshold: float,
        embedded: dict[str, int] | None = None,
    ) -> None:
        self.active_products = active_products
        self.documents = documents
        self.embedded = dict(embedded or {})
        # An empty catalog is reported as not ready. There is nothing to find either way, but it
        # keeps "ready" meaning "there is positive evidence the index is populated" rather than
        # "nothing has contradicted it yet" — which is what makes a stale value safe.
        self.ready = active_products > 0 and documents / active_products >= threshold
        self._semantic_ready = {
            slot
            for slot, count in self.embedded.items()
            if active_products > 0 and count / active_products >= threshold
        }

    def semantic(self, slot: str) -> bool:
        """Whether the semantic leg may read this slot's column.

        A slot nobody reported on is not ready, for the same reason the document gate defaults
        closed: reading a column that is empty or half-written returns a worse answer than not
        reading it, and here "worse" means plausible neighbours rather than nothing.
        """
        return slot in self._semantic_ready
