from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IndexCoverage:
    ready: bool = False
    active_products: int = 0
    documents: int = 0
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
        self.ready = active_products > 0 and documents / active_products >= threshold
        self._semantic_ready = {
            slot
            for slot, count in self.embedded.items()
            if active_products > 0 and count / active_products >= threshold
        }

    def semantic(self, slot: str) -> bool:
        return slot in self._semantic_ready
