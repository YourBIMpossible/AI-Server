#!/usr/bin/env bash
# Bring the AI-Server endpoint up and warm (WP-E). Idempotent: safe at boot and by hand.
#
#   scripts/up.sh              # systemd-managed runner: wait for the endpoint, pull what
#                              # config/models.txt lists but isn't served, warm INFERENCE_MODEL
#   scripts/up.sh --compose    # container runner: docker compose up -d first
#   scripts/up.sh --model M    # warm M instead (repeatable); extra args go to preload.py
#
# Talks to INFERENCE_BASE_URL (repo .env, else localhost). On the box itself that is the
# runner's loopback address, not the gateway.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

if [ "${1:-}" = "--compose" ]; then
  shift
  docker compose -f "$ROOT/docker-compose.yml" up -d
fi

exec "$PY" "$ROOT/scripts/preload.py" --wait 300 --pull "$@"
