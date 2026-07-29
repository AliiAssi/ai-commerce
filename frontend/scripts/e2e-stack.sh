#!/usr/bin/env bash
# Brings up everything the Playwright suite needs, runs it, and tears the stack down again.
#
#   ./scripts/e2e-stack.sh              run the suite
#   ./scripts/e2e-stack.sh --ui         run it in Playwright's UI mode
#
# The database is a throwaway container on a non-default port, so it can never touch a real
# one. CI does not use this script: its frontend job already has Postgres and the API running.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER=beit-e2e-pg
PG_PORT=55450
API_PORT=8010
AI_PORT=8011
export DATABASE_URL="postgresql://postgres:postgres@localhost:${PG_PORT}/beit_e2e"
export JWT_SECRET="e2e-secret-0123456789abcdefghijkl"
export ENVIRONMENT=development
export SEED_ADMIN_EMAIL="admin@beit.test"
export SEED_ADMIN_PASSWORD="Password#123"
export API_BASE_URL="http://127.0.0.1:${API_PORT}"

# The AI service owns retrieval, so the search half of the storefront cannot be exercised
# without it running. Routing is enabled here and nowhere else by default: this is the only
# place the whole chain — browser, Next, web, ai, database — is proven end to end.
export INTERNAL_API_KEY="e2e-internal-key-0123456789"
export MCP_BEARER_TOKEN="e2e-mcp-token-0123456789"
export OLLAMA_API_KEY="e2e-unused"   # chat is not driven by this suite
export AI_SERVICE_URL="http://127.0.0.1:${AI_PORT}"
export SMART_SEARCH_ROUTING_ENABLED=true

api_pid=""
ai_pid=""
cleanup() {
  [ -n "$api_pid" ] && kill "$api_pid" 2>/dev/null || true
  [ -n "$ai_pid" ] && kill "$ai_pid" 2>/dev/null || true
  docker stop "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# pgvector/pgvector, not stock postgres: the migrations create the `vector` and `pg_trgm`
# extensions and will fail loudly on an image that lacks them.
echo "==> postgres"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --rm --name "$CONTAINER" \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=beit_e2e \
  -p "${PG_PORT}:5432" pgvector/pgvector:pg18 >/dev/null
for _ in $(seq 1 60); do
  docker exec "$CONTAINER" pg_isready -U postgres -d beit_e2e >/dev/null 2>&1 && break
  sleep 1
done

echo "==> migrate and seed"
cd "$REPO_ROOT/web"
uv run alembic upgrade head >/dev/null
uv run python -m app.application.jobs.seed_catalog >/dev/null
# ai's tables carry foreign keys into the catalog, so web migrates first.
cd "$REPO_ROOT/ai"
uv run alembic upgrade head >/dev/null
# §11: the seed workflow runs the backfill. The in-process worker would get there on its own
# within a sweep, but the suite starts querying immediately — without this every search would
# silently answer from §12's step 4 and the document leg would never be exercised end to end.
uv run python -m app.application.jobs.reindex_catalog --all >/dev/null

echo "==> api on :${API_PORT}"
cd "$REPO_ROOT/web"
uv run uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >/tmp/beit-e2e-api.log 2>&1 &
api_pid=$!
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${API_PORT}/healthz" >/dev/null 2>&1 && break
  sleep 1
done

echo "==> ai on :${AI_PORT}"
cd "$REPO_ROOT/ai"
uv run uvicorn app.main:app --host 127.0.0.1 --port "$AI_PORT" >/tmp/beit-e2e-ai.log 2>&1 &
ai_pid=$!
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${AI_PORT}/healthz" >/dev/null 2>&1 && break
  sleep 1
done

echo "==> build"
cd "$REPO_ROOT/frontend"
npm run build

echo "==> playwright"
npx playwright test "$@"
