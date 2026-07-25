# CI

[workflows/ci.yml](workflows/ci.yml) runs on every push and every pull request, no branch
filter. It's two independent jobs, `web` and `ai`, one per service — they run in parallel
and either can fail without blocking the other.

Each job does the same four things:

1. Spins up a throwaway Postgres 17 container as a GitHub Actions service (not the real
   database — it only exists for the duration of the job).
2. Installs dependencies with `uv sync --frozen`, so CI uses exactly what's pinned in the
   lockfile, never a resolved-on-the-fly version.
3. Lints with `ruff check` and `ruff format --check` — a formatting diff fails the build,
   it doesn't just warn.
4. Runs `pytest` (unit + integration) against the throwaway Postgres.

The `ai` job also runs `uv sync` inside `web/` before testing, because `ai`'s integration
tests read the store schema through migrations that live in `web/`.

Nothing here needs a GitHub secret — the Postgres credentials are hardcoded test-only
values, and no external service (Ollama, Render) is called during CI.

## Next steps

- **No status badge.** Once pushed, add a badge to the root README so CI health is
  visible without opening the Actions tab.
- **No dependency caching.** Each run does a full `uv sync` from scratch; `astral-sh/setup-uv`
  supports cache restore between runs, which would cut job time once this repo sees
  regular traffic.
