# ai — AI service (shopping assistant + MCP server)

A FastAPI service, in the same layered structure as `web/`, that exposes two things
over one shared set of tools:

- an **MCP server** at `/mcp` (Streamable HTTP) that any MCP client can connect to —
  Claude Code, Claude Desktop, MCP Inspector, or your own agent;
- a **shopping assistant** at `POST /chat` (streaming responses) powered by Ollama
  Cloud, using live store data to answer questions.

This service only reads the store's database. It owns just its own `ai_*` tables.

## Setup

```bash
cd ai
uv sync
cp ../.env.example ../.env # one shared .env at the repo root, used by both services
```

Required in the root `.env`: `DATABASE_URL` (same database as web — any Postgres works,
Neon recommended), `OLLAMA_API_KEY`, `MCP_BEARER_TOKEN` (min 16 chars), and
`INTERNAL_API_KEY` (min 16 chars, same value web uses). `OLLAMA_MODEL` defaults to
`gemma4:31b-cloud` (must support tool calling).

## Run

```bash
uv run alembic upgrade head                      # create ai_* tables
uv run uvicorn app.main:app --reload --port 8001 # http://127.0.0.1:8001
```

Endpoints:

| Method | Path       | Auth                     | Purpose                          |
|--------|------------|--------------------------|----------------------------------|
| GET    | `/healthz` | none                     | liveness + non-fatal DB probe    |
| POST   | `/chat`    | `X-Internal-Key`         | SSE shopping assistant           |
| *      | `/mcp`     | `Authorization: Bearer`  | MCP Streamable HTTP endpoint     |

## Test & lint

```bash
uv run pytest                                    # unit only (integration auto-skips)
TEST_DATABASE_URL=postgresql://... uv run pytest # + integration (runs web + ai migrations)
uv run ruff check . && uv run ruff format --check .
```

## Verify live

Seed the dev database from `web/` first (`uv run python -m app.application.jobs.seed_catalog`),
start the server, then:

```bash
uv run python scripts/live_smoke.py              # real Ollama chat + real tool call
```

Connect an MCP client to the local server:

```bash
# MCP Inspector — Streamable HTTP, http://127.0.0.1:8001/mcp, header Authorization: Bearer <token>
npx @modelcontextprotocol/inspector

# Claude Code
claude mcp add --transport http shop http://127.0.0.1:8001/mcp \
  --header "Authorization: Bearer $MCP_BEARER_TOKEN"
```

Both list `search_products`, `get_product`, `list_categories`, `get_order`, `list_orders`,
`get_order_status`, `store_stats`, `top_rated_products`, `low_stock_products`, plus the
`store://overview` resource and `shopping_assistant` prompt.
