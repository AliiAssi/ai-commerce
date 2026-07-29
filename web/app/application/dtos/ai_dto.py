from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.application.dtos.product_dto import DegradedReason, SearchMode, SortOption


@dataclass
class ChatStreamHandle:
    session_id: str | None
    frames: AsyncIterator[bytes]


class RemoteSearchResult(BaseModel):
    """What the AI service returned, validated at the boundary.

    Parsing the response into this model is what makes the gateway's contract honest: a
    malformed or partial payload fails validation and is treated as an outage, so web falls
    back to lexical rather than serving a half-populated page.
    """

    product_ids: list[int]
    total: int
    page: int
    page_size: int

    query: str
    language: str
    mode: SearchMode
    reranked: bool = False
    effective_sort: SortOption
    inferred_filters: dict[str, str] = Field(default_factory=dict)
    ignored_inferred: list[str] = Field(default_factory=list)
    degraded: bool = False
    degraded_reason: DegradedReason | None = None
