#!/usr/bin/env bash
# Start local LGTM observability stack (ADR-0051).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
ENV_FILE="$ROOT_DIR/infra/compose/observability/.env"
ENV_EXAMPLE="$ROOT_DIR/infra/compose/observability/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "observability-up: created $ENV_FILE from .env.example"
fi

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$2"
    exit 1
  fi
}

require_tool docker "docker is required for observability-up."

docker compose -f "$COMPOSE" --env-file "$ENV_FILE" up -d
echo "observability-up: Grafana http://localhost:${IBEX_OBS_GRAFANA_PORT:-3000} (anonymous Admin)"
echo "observability-up: Prometheus http://localhost:${IBEX_OBS_PROMETHEUS_PORT:-9090}"
echo "observability-up: OTLP gRPC localhost:${IBEX_OBS_OTLP_GRPC_PORT:-4317} (set OTEL_EXPORTER_OTLP_ENDPOINT=127.0.0.1:4317)"
