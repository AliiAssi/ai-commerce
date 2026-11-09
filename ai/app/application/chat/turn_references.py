from __future__ import annotations

from typing import Any

from app.application.dtos.reference_dto import MoreResultsDTO, ProductCardDTO
from app.core.links import category_ref, ref_kind, ref_path, tracked


class TurnReferences:
    def __init__(self) -> None:
        self._known: set[str] = set()
        self._products: dict[int, dict[str, Any]] = {}
        self._searches: list[tuple[str, int, list[int]]] = []
        self._cited: list[int] = []

    def collect(self, result: Any) -> None:
        self._walk(result)

    def resolve(self, ref: str) -> str | None:
        if ref not in self._known:
            return None
        path = ref_path(ref)
        if path is None:
            return None
        if ref_kind(ref) == "product":
            product_id = int(ref.partition(":")[2])
            if product_id not in self._cited:
                self._cited.append(product_id)
        return tracked(path, "chat")

    def cards(self, limit: int) -> list[ProductCardDTO]:
        cards = []
        for product_id in self._cited[:limit]:
            product = self._products[product_id]
            url = tracked(ref_path(product["ref"]) or "", "chat")
            cards.append(ProductCardDTO.model_validate({**product, "url": url}))
        return cards

    def more(self, shown: int) -> MoreResultsDTO | None:
        if not shown:
            return None
        cited = set(self._cited[:shown])
        for ref, total, product_ids in reversed(self._searches):
            if cited.intersection(product_ids):
                if total <= shown:
                    return None
                return MoreResultsDTO(total=total, url=tracked(ref_path(ref), "chat"))
        return None

    def _walk(self, node: Any) -> list[int]:
        if isinstance(node, list):
            return [pid for item in node for pid in self._walk(item)]
        if not isinstance(node, dict):
            return []

        found = [pid for value in node.values() for pid in self._walk(value)]
        ref = node.get("ref")
        kind = ref_kind(ref) if isinstance(ref, str) else None
        if kind is None:
            return found

        self._known.add(ref)
        if kind == "product":
            self._products[node["id"]] = node
            if node.get("category_slug"):
                self._known.add(category_ref(node["category_slug"]))
            found.append(node["id"])
        elif kind == "search":
            self._searches.append((ref, int(node.get("total") or 0), found))
        return found
