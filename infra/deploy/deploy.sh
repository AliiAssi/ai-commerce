#!/usr/bin/env bash
# Runs on the VM. GitHub Actions reaches it through an SSH key whose authorized_keys entry
# forces this script, passing the commit sha as SSH_ORIGINAL_COMMAND.
set -euo pipefail

REPO=/home/username/ai-commerce
UV=/home/username/.local/bin/uv
NGINX_SITE=/etc/nginx/sites-available/ai-commerce
UNIT_DIR=/etc/systemd/system
PUBLIC_HOST=ai-commerce.duckdns.org
LOCK=/tmp/beit-deploy.lock

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() {
  log "FAILED: $*"
  exit 1
}

touched() { grep -q "^$1" <<<"$CHANGED"; }

wait_healthy() {
  for _ in $(seq 1 30); do
    curl -fs -o /dev/null --max-time 5 "$@" && return 0
    sleep 1
  done
  log "not healthy: ${*: -1}"
  return 1
}

apply_units() {
  log "systemd: verifying and installing units"
  sudo systemd-analyze verify "$REPO"/infra/systemd/*.service || return 1
  sudo install -m 644 -o root -g root "$REPO"/infra/systemd/*.service "$UNIT_DIR"/ || return 1
  sudo systemctl daemon-reload
}

apply_nginx() {
  log "nginx: installing and testing config"
  local backup
  backup=$(mktemp)
  sudo cp "$NGINX_SITE" "$backup" || return 1
  sudo install -m 600 -o root -g root "$REPO/infra/nginx/ai-commerce.conf" "$NGINX_SITE" || return 1
  if ! sudo /usr/sbin/nginx -t -q; then
    log "nginx: config test failed, restoring the previous config"
    sudo install -m 600 -o root -g root "$backup" "$NGINX_SITE"
    rm -f "$backup"
    return 1
  fi
  rm -f "$backup"
  sudo systemctl reload nginx || return 1
  wait_healthy --resolve "$PUBLIC_HOST:443:127.0.0.1" "https://$PUBLIC_HOST/healthz"
}

sync_service() {
  log "$1: uv sync"
  (cd "$REPO/$1" && "$UV" sync --locked --quiet)
}

migrate() {
  local service
  for service in web ai; do
    log "$service: alembic upgrade head"
    (cd "$REPO/$service" && "$UV" run --no-sync alembic upgrade head) || return 1
  done
}

restart_checked() {
  log "$1: restarting"
  sudo systemctl restart "$1" || return 1
  wait_healthy "http://127.0.0.1:$2/healthz"
}

apply_changes() {
  local mode=$1 restart_web=false restart_ai=false
  if touched infra/systemd/; then
    apply_units || return 1
    restart_web=true
    restart_ai=true
  fi
  if touched web/; then
    sync_service web || return 1
    restart_web=true
  fi
  if touched ai/; then
    sync_service ai || return 1
    restart_ai=true
  fi
  if [[ $mode == forward ]] && { touched web/ || touched ai/; }; then
    migrate || return 1
  fi
  if $restart_web; then restart_checked web 8000 || return 1; fi
  if $restart_ai; then restart_checked ai 8001 || return 1; fi
  if touched infra/nginx/; then apply_nginx || return 1; fi
  return 0
}

apply() {
  local previous=$1 target=$2
  cd "$REPO"
  CHANGED=$(git diff --name-only "$previous" "$target")
  log "deploying ${target:0:7} over ${previous:0:7}"
  if ! touched infra/systemd/ && ! touched infra/nginx/ && ! touched web/ && ! touched ai/; then
    log "nothing to apply on the VM for this change"
    return 0
  fi
  if apply_changes forward; then
    log "done: ${target:0:7} is live"
    return 0
  fi
  log "rolling back to ${previous:0:7} (database migrations are not reverted)"
  git reset --hard --quiet "$previous"
  apply_changes rollback || log "rollback also failed, the VM needs a look"
  die "deploy of ${target:0:7} failed and was rolled back"
}

deploy() {
  local target=$1
  [[ $target =~ ^[0-9a-f]{40}$ ]] || die "expected a full commit sha, got '$target'"

  exec 9>"$LOCK"
  flock -w 900 9 || die "another deploy is still running"

  cd "$REPO"
  [[ -z $(git status --porcelain) ]] || die "the VM checkout has local changes"
  git fetch --quiet origin main
  git merge-base --is-ancestor "$target" origin/main || die "${target:0:7} is not on origin/main"

  local previous
  previous=$(git rev-parse HEAD)
  if git merge-base --is-ancestor "$target" "$previous"; then
    log "${target:0:7} is already deployed (the VM is at ${previous:0:7})"
    return 0
  fi

  git reset --hard --quiet "$target"
  exec "$REPO/infra/deploy/deploy.sh" --apply "$previous" "$target"
}

if [[ ${1:-} == --apply ]]; then
  apply "$2" "$3"
else
  deploy "${SSH_ORIGINAL_COMMAND:-${1:-}}"
fi
