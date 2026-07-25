from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class ChatStreamHandle:
    session_id: str | None
    frames: AsyncIterator[bytes]
