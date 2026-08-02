from __future__ import annotations

import pytest
import yaml

from app.core.prompts import PROMPTS_PATH, REQUIRED_KEYS, PromptLibrary, load_prompts


def test_shipped_prompts_load_and_cover_required_keys() -> None:
    library = load_prompts()
    for key in REQUIRED_KEYS:
        placeholders = {"store_name": "TestMart"} if "{store_name}" in _raw(key) else {}
        assert library.render(key, **placeholders)


def test_system_prompt_renders_store_name() -> None:
    library = load_prompts()
    rendered = library.render("chat.system", store_name="TestMart")
    assert "TestMart" in rendered


def test_missing_required_key_is_rejected(tmp_path) -> None:
    incomplete = tmp_path / "prompts.yaml"
    incomplete.write_text("chat:\n  system: hi\n", encoding="utf-8")
    with pytest.raises(KeyError, match="missing required keys"):
        load_prompts(incomplete)


def test_unknown_key_and_missing_placeholder_raise() -> None:
    library = PromptLibrary({"greet": "hello {name}"})
    with pytest.raises(KeyError):
        library.render("nope")
    with pytest.raises(KeyError):
        library.render("greet")
    assert library.render("greet", name="sam") == "hello sam"


def test_literal_braces_and_dollars_survive_rendering() -> None:
    library = PromptLibrary({"example": 'reply {"ok": true} for {store_name} under $20'})
    assert library.render("example", store_name="BEIT") == 'reply {"ok": true} for BEIT under $20'


def _raw(key: str) -> str:
    node = yaml.safe_load(PROMPTS_PATH.read_text(encoding="utf-8"))
    for part in key.split("."):
        node = node[part]
    return node
