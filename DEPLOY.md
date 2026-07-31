# Deploying BEIT

Platform-neutral. Two Python services plus a Next.js frontend, one PostgreSQL database with
`pgvector`.

## 0. Before anything

The database must have the `pgvector` extension available. The migrations issue
`CREATE EXTENSION IF NOT EXISTS vector` themselves, but the extension has to be installable on the
instance. Neon, Supabase and RDS all support it; a stock managed Postgres may not.

Check with:

```sql
SELECT * FROM pg_available_extensions WHERE name IN ('vector', 'pg_trgm');
```

Both must be listed. `pg_trgm` powers fuzzy spelling matches; `vector` powers semantic search.

## 1. Migration order — this is not optional

`web` owns `products` and `categories`. `ai` owns the search tables, and those carry real foreign
keys into `products`. Run them in this order or ai's migration fails:

```bash
cd web && DATABASE_URL=... uv run alembic upgrade head    # first
cd ai  && DATABASE_URL=... uv run alembic upgrade head    # second
```

Migrations need `DATABASE_URL` and nothing else — no JWT secret, no API keys. That is deliberate
and there is a test in each service pinning it.

Confirm afterwards:

```sql
SELECT version_num FROM alembic_version;      -- web, expect 0004
SELECT version_num FROM ai_alembic_version;   -- ai,  expect 0003
```

If `ai_alembic_version` says `0002`, the vector columns do not exist and semantic search cannot
work no matter what the flags say.

## 2. Environment variables

### web

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string |
| `JWT_SECRET` | yes | min 32 chars |
| `INTERNAL_API_KEY` | yes | must match ai's value exactly |
| `AI_SERVICE_URL` | yes | private URL of the ai service |
| `SMART_SEARCH_ROUTING_ENABLED` | — | `false` until step 5 |
| `SEARCH_TIMEOUT_SECONDS` | — | default 8.0 |
| `ENVIRONMENT` | — | `production` |

### ai

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | the same database |
| `INTERNAL_API_KEY` | yes | must match web's |
| `MCP_BEARER_TOKEN` | yes | min 16 chars, for external MCP clients |
| `OLLAMA_API_KEY` | yes | the chat model |
| `SMART_SEARCH_ENABLED` | — | `false` until step 5 |
| `EMBEDDING_PROVIDER` | for search | `gemini` |
| `EMBEDDING_HOST` | for search | `https://generativelanguage.googleapis.com` |
| `EMBEDDING_API_KEY` | for search | |
| `EMBEDDING_MODEL` | for search | `gemini-embedding-001` |
| `EMBEDDING_DIMENSIONS` | for search | **768** — must match the migration, see below |
| `RERANKER_PROVIDER` | optional | `openrouter`, or empty to skip reranking |
| `RERANKER_MODEL` | optional | `nvidia/llama-nemotron-rerank-vl-1b-v2:free` |
| `RERANKER_API_KEY` | optional | |
| `PUBLIC_HOSTNAME` | optional | appended to the MCP allow-lists |

**`EMBEDDING_DIMENSIONS` is not a free choice.** The columns are `vector(768)`. A different value
is refused at startup, because the mismatch would otherwise surface as a failed write after a
backfill had already been paid for.

### frontend

| Variable | Notes |
|---|---|
| `API_BASE_URL` | public URL of the web service |
| `AI_ENABLED` | `true` to show the chat widget |

## 3. Seed and build the index

```bash
cd web && DATABASE_URL=... uv run python -m app.application.jobs.seed_catalog
cd ai  && DATABASE_URL=... SMART_SEARCH_ENABLED=true \
          uv run python -m app.application.jobs.reindex_catalog --all
```

Expect `46/46 active products` and `46/46 (primary)` vectors. 46 products is three batched
embedding calls and a few seconds.

In normal running you do not need this step — the index worker inside the ai service fills and
maintains the index on its own. It is only needed for a first deploy or after a catalog reseed.

## 4. Check before turning anything on

```bash
curl -s https://<ai-host>/health
curl -s -X POST https://<ai-host>/search \
  -H "X-Internal-Key: $INTERNAL_API_KEY" -H "Content-Type: application/json" \
  -d '{"q":"copper"}'
```

The search endpoint is authenticated and is never reachable from a browser. A 200 with
`product_ids` means retrieval works even while the public flag is off.

## 5. Turn it on, in this order

1. `SMART_SEARCH_ENABLED=true` on **ai**, restart, confirm `/search` reports
   `"mode": "hybrid"` rather than `"lexical"`.
2. `SMART_SEARCH_ROUTING_ENABLED=true` on **web**, restart.

Never the reverse. Web routing to an ai service that has search switched off gives you lexical
results over an extra network hop — slower than not routing at all.

## 6. Free-tier limits that will bite

| Service | Limit | What happens at the limit |
|---|---|---|
| Gemini embeddings | 1,000 requests/day | Search degrades to lexical. Arabic queries return little or nothing |
| OpenRouter `:free` reranker | **50 requests/day** without credits, 1,000 with any credit purchased | Reranking stops; the fused order is served |

The reranker limit is the sharp one. Every search that reranks costs one call, so a demo session
can exhaust 50 quickly and you would be showing the fallback without noticing. Either buy the
minimum credit or leave `RERANKER_PROVIDER` empty in production.

Query embeddings are cached in the database, so repeat searches cost nothing.

## 7. Health of a running deploy

```sql
SELECT count(*) FROM ai_search_documents;                          -- expect 46
SELECT count(*) FROM ai_search_documents WHERE embedding IS NOT NULL;  -- expect 46
SELECT count(*) FROM ai_search_index_jobs;                         -- expect 0 when idle
```

A non-empty job table that never drains means the worker is failing. Job rows carry
`last_error_code`; anything prefixed `embedding_` is a provider problem rather than a database one.

## Notes

- Both services run one process. The ai service also runs the index worker in-process, so it needs
  no separate worker service.
- The connection pool is small on purpose (2 + 3 overflow per service). Both services share one
  database, so raising it needs the database's own limit checked first.
- `tests/` is not needed at runtime. The ai service starts and serves with the whole folder absent.
