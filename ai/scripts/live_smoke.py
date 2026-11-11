from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.application.llm.llm_dtos import LLMMessageDTO
from app.core.config import get_settings
from app.core.registry import LLM_PROVIDERS


async def _ping_llm() -> None:
    settings = get_settings()
    print(f"[1/2] {settings.LLM_PROVIDER} ping ({settings.LLM_MODEL})...")
    client = LLM_PROVIDERS[settings.LLM_PROVIDER](settings)
    reply = await client.chat(
        [LLMMessageDTO(role="user", content="Reply with the single word: ok")]
    )
    print(
        f"      ok — {reply.usage.prompt_tokens} prompt / "
        f"{reply.usage.completion_tokens} completion tokens"
    )


async def _chat(base_url: str) -> None:
    settings = get_settings()
    print("[2/2] Chat agent loop (expects a real tool call)...")
    saw_tool = False
    saw_done = False
    async with (
        httpx.AsyncClient(timeout=httpx.Timeout(120)) as client,
        client.stream(
            "POST",
            f"{base_url}/chat",
            headers={"X-Internal-Key": settings.INTERNAL_API_KEY},
            json={"message": "What is the cheapest product you sell right now?"},
        ) as response,
    ):
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: ") :])
            if event["type"] == "token":
                print(event["text"], end="", flush=True)
            elif event["type"] == "tool":
                saw_tool = True
                print(f"\n      [tool] {event['name']}")
            elif event["type"] == "done":
                saw_done = True
            elif event["type"] == "error":
                print(f"\n      [error] {event['message']}")
    print()
    if not (saw_tool and saw_done):
        sys.exit(f"FAIL: expected a tool call and a done event (tool={saw_tool}, done={saw_done})")
    print("      ok — real tool call + completed stream")


async def _main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    await _ping_llm()
    await _chat(base_url)
    print("\nSMOKE PASSED")


if __name__ == "__main__":
    asyncio.run(_main())
