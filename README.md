# ai-commerce

An ecommerce storefront with a built-in AI shopping assistant, split into three independent
services:

- **[`frontend/`](frontend/README.md)** — the user interface. Next.js 16 (App Router), React 19,
  Tailwind v4. Storefront, cart and checkout, account, admin, and the assistant widget. The
  only thing a browser ever talks to.
- **[`web/`](web/README.md)** — the store. A FastAPI JSON API under `/api/v1`: catalog, cart,
  checkout, orders, reviews, users, admin operations, and a proxy to the AI service.
- **[`ai/`](ai/README.md)** — the AI service. A chat-based shopping assistant answering from
  live store data (products, prices, stock, a signed-in customer's own orders), plus an MCP
  server at `/mcp` so any MCP client — Claude Code, Claude Desktop, MCP Inspector, a custom
  agent — can query the store the same way.

```
browser ──httpOnly cookie──▶ frontend ──Bearer──▶ web ──X-Internal-Key──▶ ai
                                                              │
                                                          Postgres
```

The session lives in an httpOnly cookie set by `frontend/`, which calls `web/` server-side.
The API's address and the token never reach the browser, so there is no CORS anywhere in the
repo. `ai/` never faces the browser at all, never sees more of a customer's data than their
own orders, and its credentials stay inside `web/`.

Built with Next.js, FastAPI, SQLAlchemy, Ollama Cloud and Postgres. Deploying to Render and
Vercel is supported but optional — everything runs locally against any Postgres.

The catalog ships seeded with demo data: real Lebanese goods (olive oil, ceramics, textiles
and more) standing in for a real catalog.

## Run locally

Order matters — `web/` seeds the catalog that both other services read.

```bash
# 1. the store
cd web && uv sync
cp ../.env.example ../.env          # one shared .env at the repo root
uv run alembic upgrade head
uv run python -m app.application.jobs.seed_catalog
uv run uvicorn app.main:app --reload            # :8000

# 2. the UI
cd ../frontend && nvm use && npm install
cp .env.example .env.local          # API_BASE_URL points at :8000
npm run dev                                      # :3000

# 3. optional — the assistant
cd ../ai && uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8001
```

The Python services share **one** `.env` at the repo root; `frontend/` has its own
`.env.local`, because it needs different values and must never be handed the AI keys.

Without `AI_SERVICE_URL` + `INTERNAL_API_KEY` the store runs normally and the assistant simply
reports itself unavailable; set `AI_ENABLED=false` in `frontend/` to hide the widget entirely.

## Tests

| Service | Command | Needs |
|---|---|---|
| `web/` | `uv run pytest` | `TEST_DATABASE_URL` for the integration half, else it skips |
| `ai/` | `uv run pytest` | same |
| `frontend/` | `npm run test` | nothing — `fetch` is stubbed |
| `frontend/` | `npm run test:e2e:stack` | Docker; brings up its own Postgres and API |

The end-to-end suite is the one that catches the bugs the others structurally cannot — see
[frontend/tests/e2e/README.md](frontend/tests/e2e/README.md).

## CI

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs three jobs on every push: `web`,
`ai`, and `frontend`. Each Python job gets a throwaway Postgres. The `frontend` job also
stands up the API, because `next build` prerenders real product pages and the Playwright suite
drives a real browser — so a broken prerender or a broken flow fails the PR, not the deploy.

[.github/workflows/keep-warm.yml](.github/workflows/keep-warm.yml) pings both Python services
every five hours to blunt Render's free-tier cold starts.
