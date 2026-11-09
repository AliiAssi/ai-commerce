from __future__ import annotations

import re
from collections.abc import Callable

_MAX_HOLD = 300
_LINK = re.compile(r"(!?)\[([^\[\]\n]*)\]\(([^()\s]*)\)")
_PARTIAL = re.compile(r"!?\[[^\[\]\n]*(?:\](?:\([^()\s]*)?)?")


def _candidate(text: str) -> int:
    start = text.find("[")
    if start > 0 and text[start - 1] == "!":
        return start - 1
    return start


class LinkRewriter:
    def __init__(self, resolve: Callable[[str], str | None]) -> None:
        self._resolve = resolve
        self._pending = ""
        self._canonical: list[str] = []

    @property
    def canonical(self) -> str:
        return "".join(self._canonical)

    def feed(self, text: str) -> str:
        self._pending += text
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> str:
        display: list[str] = []

        def emit(shown: str, kept: str | None = None) -> None:
            display.append(shown)
            self._canonical.append(shown if kept is None else kept)

        buffer = self._pending
        while buffer:
            start = _candidate(buffer)
            if start == -1:
                if not final and buffer.endswith("!"):
                    emit(buffer[:-1])
                    buffer = "!"
                else:
                    emit(buffer)
                    buffer = ""
                break

            emit(buffer[:start])
            buffer = buffer[start:]

            match = _LINK.match(buffer)
            if match:
                image, label, target = match.groups()
                href = None if image else self._resolve(target)
                if href:
                    emit(f"[{label}]({href})", f"[{label}]({target})")
                else:
                    emit(label)
                buffer = buffer[match.end() :]
                continue

            if not final and len(buffer) < _MAX_HOLD and _PARTIAL.fullmatch(buffer):
                break

            literal = 2 if buffer.startswith("![") else 1
            emit(buffer[:literal])
            buffer = buffer[literal:]

        self._pending = buffer
        return "".join(display)
