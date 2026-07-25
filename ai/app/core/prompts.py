from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

PROMPTS_PATH = Path(__file__).with_name("prompts.yaml")

REQUIRED_KEYS = (
    "chat.system",
    "chat.session_limit_reply",
    "mcp.shopping_assistant",
    "errors.llm_unavailable",
)


class PromptLibrary:
    def __init__(self, prompts: dict[str, str]) -> None:
        self._prompts = prompts

    def render(self, key: str, **placeholders: Any) -> str:
        template = self._prompts.get(key)
        if template is None:
            raise KeyError(f"unknown prompt key {key!r}")
        return template.format(**placeholders).strip()


def _flatten(node: Any, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            flat.update(_flatten(value, f"{prefix}{key}."))
    elif isinstance(node, str):
        flat[prefix.rstrip(".")] = node
    return flat


def load_prompts(path: Path = PROMPTS_PATH) -> PromptLibrary:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    prompts = _flatten(data)
    missing = [key for key in REQUIRED_KEYS if key not in prompts]
    if missing:
        raise KeyError(f"prompts.yaml is missing required keys: {', '.join(missing)}")
    return PromptLibrary(prompts)


def load_prompts_or_exit(path: Path = PROMPTS_PATH) -> PromptLibrary:
    try:
        return load_prompts(path)
    except (KeyError, yaml.YAMLError, OSError) as exc:
        sys.exit(f"FATAL: cannot load {path.name}: {exc}")
