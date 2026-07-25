from __future__ import annotations

from app.core.config import Settings
from app.core.prompts import PromptLibrary


def register(mcp, prompts: PromptLibrary, settings: Settings) -> None:
    @mcp.prompt(
        name="shopping_assistant",
        description="Persona for a store shopping assistant grounded in the store's tools.",
    )
    def shopping_assistant() -> str:
        return prompts.render("mcp.shopping_assistant", store_name=settings.STORE_NAME)
