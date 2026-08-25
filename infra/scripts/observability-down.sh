#!/usr/bin/env bash
# Stop local LGTM observability stack.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
ENV_FILE="$ROOT_DIR/infra/compose/observability/.env"
ENV_EXAMPLE="$ROOT_DIR/infra/compose/observability/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
  ENV_FILE="$ENV_EXAMPLE"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for observability-down."
  exit 1
fi

docker compose -f "$COMPOSE" --env-file "$ENV_FILE" down
echo "observability-down: stack stopped"
