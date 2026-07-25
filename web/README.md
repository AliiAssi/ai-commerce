# web — storefront service

FastAPI + SQLAlchemy 2 (async) + Alembic, on Postgres (Neon recommended), in a layered
structure (`core`, `application`, `infrastructure`, `presentation`, `ui`). Serves the
storefront (Jinja2 + HTMX + Tailwind), an admin dashboard, JSON APIs under `/api/v1` with
interactive docs at `/docs`, and the "Ask the store" chat widget — which proxies to the
`ai/` service so the AI keys stay server-side.

## Setup

```bash
cd web
uv sync                    # creates .venv and installs everything
cp ../.env.example ../.env # one shared .env at the repo root, used by both services
```

Required in the root `.env`: `DATABASE_URL` (any Postgres works; if using Neon, use the
**direct** connection string, not the `-pooler` host) and `JWT_SECRET` (min 32 chars).
Set `AI_SERVICE_URL` + `INTERNAL_API_KEY` to enable the chat widget; without them it
stays hidden and the store works as normal.

## Run

```bash
uv run alembic upgrade head            # apply migrations
uv run python -m app.application.jobs.seed_catalog   # idempotent demo data
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```

## Test & lint

```bash
uv run pytest tests/unit               # no database needed
TEST_DATABASE_URL=postgres://... uv run pytest       # + integration suite
uv run ruff check . && uv run ruff format --check .
```

Integration tests need a **second**, separate database; they run migrations there and
truncate tables between tests. They skip cleanly when `TEST_DATABASE_URL` is unset.

## Seeded demo accounts

- admin: `admin@store.test` / `Admin#12345` (override via `SEED_ADMIN_*`)
- customers: `demo1..3@store.test` / `Demo#12345`
