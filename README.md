# ai-commerce

An ecommerce storefront with a built-in AI shopping assistant, split into two independent
FastAPI services:

- **`web/`** — the storefront. Product catalog with search, filtering and categories, a
  shopping cart, checkout, order history, product reviews, and an admin dashboard for
  managing products, orders, and stock.
- **`ai/`** — the AI service. A chat-based shopping assistant that answers questions
  using live store data (products, prices, stock, a signed-in customer's own orders), and
  an MCP server at `/mcp` so any MCP client — Claude Code, Claude Desktop, MCP Inspector,
  or a custom agent — can query the store the same way.

The two talk to each other over a private internal API; the AI service never talks to the
browser directly, and never sees more of a customer's data than their own orders. Built
with FastAPI, SQLAlchemy, Ollama Cloud, and Postgres. Deploying to Render is supported but
optional — everything also runs locally against any Postgres database.

The catalog currently ships seeded with demo data: real Lebanese products and goods
(olive oil, ceramics, textiles, and more) standing in for a real catalog.

## Run locally

Set up `web/` first — it seeds the demo catalog that `ai/` reads from. Each service has
its own README with full setup steps: [web/](web/README.md), [ai/](ai/README.md).

Both services share **one** `.env` at the repo root. The storefront's chat widget only
appears once `ai/` is also running and `AI_SERVICE_URL` + `INTERNAL_API_KEY` are set —
without them, the store works normally with the widget hidden.

## CI

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) lints and tests both
services on every push, integration tests run against a throwaway Postgres.
