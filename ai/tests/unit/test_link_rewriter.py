from __future__ import annotations

import pytest

from app.application.chat.link_rewriter import LinkRewriter

KNOWN = {"product:12": "/products/12", "category:pantry": "/catalog?category=pantry"}


def _run(chunks: list[str]) -> tuple[str, str]:
    rewriter = LinkRewriter(KNOWN.get)
    shown = "".join(rewriter.feed(chunk) for chunk in chunks) + rewriter.flush()
    return shown, rewriter.canonical


def _every_split(text: str) -> list[list[str]]:
    return [[text[:i], text[i:]] for i in range(len(text) + 1)] + [list(text)]


@pytest.mark.parametrize("chunks", _every_split("Try [Za'atar](product:12) today."))
def test_known_ref_becomes_a_link_however_the_stream_is_split(chunks: list[str]) -> None:
    shown, canonical = _run(chunks)

    assert shown == "Try [Za'atar](/products/12) today."
    assert canonical == "Try [Za'atar](product:12) today."


@pytest.mark.parametrize(
    "text",
    [
        "Try [Za'atar](product:99) today.",
        "Try [Za'atar](https://evil.example/x) today.",
        "Try [Za'atar](/products/12) today.",
        "Try ![Za'atar](product:12) today.",
    ],
)
def test_unknown_external_and_image_links_keep_only_their_text(text: str) -> None:
    for chunks in _every_split(text):
        shown, canonical = _run(chunks)
        assert shown == "Try Za'atar today."
        assert canonical == "Try Za'atar today."


@pytest.mark.parametrize(
    "text",
    [
        "Prices [in USD] only.",
        "A list: [a, b] and (c).",
        "Wow! Really!",
        "Unclosed [link](product:12",
        "Ends with [",
        "Ends with !",
        "Baklava (box of 16) costs $29.",
        "Arabic: [زعتر بري] here.",
    ],
)
def test_text_that_is_not_a_link_passes_through_untouched(text: str) -> None:
    for chunks in _every_split(text):
        shown, canonical = _run(chunks)
        assert shown == text
        assert canonical == text


def test_parentheses_in_the_label_and_several_links() -> None:
    shown, _ = _run(["[Baklava (box of 16)](product:12) and ", "[Pantry](category:pantry)"])

    assert shown == "[Baklava (box of 16)](/products/12) and [Pantry](/catalog?category=pantry)"


def test_a_link_is_held_back_until_it_closes_then_released() -> None:
    rewriter = LinkRewriter(KNOWN.get)

    assert rewriter.feed("See [Za'atar](prod") == "See "
    assert rewriter.feed("uct:12) now") == "[Za'atar](/products/12) now"


def test_an_overlong_bracket_is_released_rather_than_stalling_the_stream() -> None:
    rewriter = LinkRewriter(KNOWN.get)

    shown = rewriter.feed("[" + "x" * 400)

    assert shown == "[" + "x" * 400
