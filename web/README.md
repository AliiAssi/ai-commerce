# web — storefront service

FastAPI + SQLAlchemy 2 (async) + Alembic on Postgres, in a layered structure (`core`,
`application`, `infrastructure`, `presentation`). A pure JSON API under `/api/v1` with
interactive docs at `/docs`.

It owns the store: catalog, cart, checkout, orders, reviews, users and the admin operations —
plus a proxy to the `ai/` service, so the AI credentials stay server-side and `ai/` never
faces the browser.

**This service renders no HTML.** The user interface is a separate Next.js app in
[`frontend/`](../frontend), which calls this API server-side. Nothing in a browser talks to
this service directly, which is why it has no CORS configuration.

## Setup

```bash
cd web
uv sync                    # creates .venv and installs everything
cp ../.env.example ../.env # one shared .env at the repo root, used by both services
```

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | any Postgres. On Neon use the **direct** string, not the `-pooler` host |
| `JWT_SECRET` | yes | min 32 chars; the service refuses to boot without it |
| `AI_SERVICE_URL`, `INTERNAL_API_KEY` | no | enable the chat proxy; without them `/api/v1/ai/chat` returns `503 ai_unavailable` and the store works normally |
| `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` | no | the account `seed_catalog` promotes to admin |
| `TEST_DATABASE_URL` | no | a **second** database; the integration suite skips without it |

## Run

```bash
uv run alembic upgrade head                          # apply migrations
uv run python -m app.application.jobs.seed_catalog   # idempotent demo data
uv run uvicorn app.main:app --reload                 # http://127.0.0.1:8000/docs
```

`seed_catalog` accepts `--fresh` to truncate the store tables first.

## API

Everything lives under `/api/v1`, plus `GET /healthz` (liveness + a non-fatal DB probe).

| Area | Endpoints |
|---|---|
| auth | `POST /auth/register`, `POST /auth/login`, `GET /me` |
| catalog | `GET /products`, `GET /products/{id}`, `GET /categories` |
| reviews | `GET`/`POST /products/{id}/reviews` |
| cart | `GET /cart`, `POST /cart/items`, `PATCH`/`DELETE /cart/items/{product_id}` |
| orders | `POST /checkout`, `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel` |
| admin — read | `GET /admin/dashboard`, `/admin/orders`, `/admin/orders/status-counts`, `/admin/audit`, `/admin/products`, `/admin/products/{id}` |
| admin — write | `POST`/`PATCH /admin/products*`, `POST /admin/orders/{id}/advance-status` |
| ai | `POST /ai/chat` (SSE), `POST /ai/warm` |

Two admin endpoints exist because the public ones deliberately cannot do their job:
`GET /admin/products` reaches archived and low-stock rows that `GET /products` never exposes,
and `GET /admin/products/{id}` resolves archived products that `GET /products/{id}` 404s.

### Auth

`POST /auth/login` returns a JWT in the response body. `get_current_user` accepts it as
`Authorization: Bearer` — the cookie fallback in `core/auth.py` is a leftover from the Jinja
UI and nothing sets that cookie any more.

Admin routes go through `require_permission` in `presentation/guards.py`, which **re-reads the
account from the database on every request**, so revoking someone's admin role takes effect
immediately rather than when their token expires.

### Errors

Every failure is the same envelope, so the frontend has one shape to handle:

```json
{ "error": { "code": "not_found", "message": "Product not found", "details": null } }
```

## Test & lint

```bash
uv run pytest tests/unit                             # no database needed
TEST_DATABASE_URL=postgresql://... uv run pytest     # + integration suite
uv run ruff check . && uv run ruff format --check .
```

Integration tests need a **second**, separate database; they run migrations there and truncate
tables between tests. They skip cleanly when `TEST_DATABASE_URL` is unset — so a green run
with no output is not proof they executed. Check the count.

## Conventions

- `I`-prefixed interfaces (`IFoo` in `ifoo.py`, implementation `Foo` in `foo.py`).
- DTOs are the only type that crosses a layer boundary.
- `presentation` depends on `iservices` only; `application` depends on `irepositories`, never
  on SQLAlchemy. Services own transactions.
- No `__init__.py` anywhere; every module opens `from __future__ import annotations`.

## Seeded demo accounts

- admin: `admin@store.test` / `Admin#12345` (override via `SEED_ADMIN_*`)
- customers: `demo1..3@store.test` / `Demo#12345`
