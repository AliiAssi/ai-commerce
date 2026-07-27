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
export DATABASE_URL="postgresql://postgres:postgres@localhost:${PG_PORT}/beit_e2e"
export JWT_SECRET="e2e-secret-0123456789abcdefghijkl"
export ENVIRONMENT=development
export SEED_ADMIN_EMAIL="admin@beit.test"
export SEED_ADMIN_PASSWORD="Password#123"
export API_BASE_URL="http://127.0.0.1:${API_PORT}"

api_pid=""
cleanup() {
  [ -n "$api_pid" ] && kill "$api_pid" 2>/dev/null || true
  docker stop "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> postgres"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --rm --name "$CONTAINER" \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=beit_e2e \
  -p "${PG_PORT}:5432" postgres:17 >/dev/null
for _ in $(seq 1 60); do
  docker exec "$CONTAINER" pg_isready -U postgres -d beit_e2e >/dev/null 2>&1 && break
  sleep 1
done

echo "==> migrate and seed"
cd "$REPO_ROOT/web"
uv run alembic upgrade head >/dev/null
uv run python -m app.application.jobs.seed_catalog >/dev/null

echo "==> api on :${API_PORT}"
uv run uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >/tmp/beit-e2e-api.log 2>&1 &
api_pid=$!
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${API_PORT}/healthz" >/dev/null 2>&1 && break
  sleep 1
done

echo "==> build"
cd "$REPO_ROOT/frontend"
npm run build

echo "==> playwright"
npx playwright test "$@"
