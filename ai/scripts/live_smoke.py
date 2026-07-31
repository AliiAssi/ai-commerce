from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings


async def _ping_ollama() -> None:
    settings = get_settings()
    print(f"[1/2] Ollama Cloud ping ({settings.OLLAMA_MODEL})...")
    async with httpx.AsyncClient(
        base_url=settings.OLLAMA_HOST,
        headers={"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"},
        timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS),
    ) as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
                "stream": False,
                "think": False,
            },
        )
        response.raise_for_status()
        data = response.json()
    print(
        f"      ok — {data.get('prompt_eval_count', 0)} prompt / "
        f"{data.get('eval_count', 0)} completion tokens"
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
    await _ping_ollama()
    await _chat(base_url)
    print("\nSMOKE PASSED")


if __name__ == "__main__":
    asyncio.run(_main())
