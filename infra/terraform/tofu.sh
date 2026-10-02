#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export CLOUDSDK_CONFIG="$PWD/.gcloud"

if [[ "${1:-}" == "login" ]]; then
  exec gcloud auth login
fi

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)"
export GOOGLE_OAUTH_ACCESS_TOKEN

exec tofu "$@"
