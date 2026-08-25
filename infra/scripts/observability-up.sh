#!/usr/bin/env bash
# Start local LGTM observability stack (ADR-0051).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
ENV_FILE="$ROOT_DIR/infra/compose/observability/.env"
ENV_EXAMPLE="$ROOT_DIR/infra/compose/observability/.env.example"
SECRETS_DIR="$ROOT_DIR/infra/monitoring/prometheus/scrape-auth"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "observability-up: created $ENV_FILE from .env.example"
fi

# Load the same dotenv Compose will use so printed URLs match bound ports.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$2"
    exit 1
  fi
}

require_tool docker "docker is required for observability-up."

mkdir -p "$SECRETS_DIR"
# Bearer for embedder /metrics scrapes (credentials_file; never commit the file).
umask 077
printf '%s' "${IBEX_EMBEDDING_METRICS_BEARER:-dev-embedder-metrics-token}" \
  >"$SECRETS_DIR/embedder_metrics_bearer"

docker compose -f "$COMPOSE" --env-file "$ENV_FILE" up -d

GRAFANA_PORT="${IBEX_OBS_GRAFANA_PORT:-3000}"
PROM_PORT="${IBEX_OBS_PROMETHEUS_PORT:-9090}"
OTLP_PORT="${IBEX_OBS_OTLP_GRPC_PORT:-4317}"

# Prefer Docker-reported host ports when available (matches actual bind).
published_port() {
  local service="$1" container_port="$2" mapped
  mapped="$(docker compose -f "$COMPOSE" --env-file "$ENV_FILE" port "$service" "$container_port" 2>/dev/null || true)"
  if [[ "$mapped" =~ :([0-9]+)$ ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi
  return 1
}
if gp="$(published_port grafana 3000)"; then GRAFANA_PORT="$gp"; fi
if pp="$(published_port prometheus 9090)"; then PROM_PORT="$pp"; fi
if op="$(published_port otel-collector 4317)"; then OTLP_PORT="$op"; fi

echo "observability-up: Grafana http://127.0.0.1:${GRAFANA_PORT} (loopback; anonymous Viewer)"
echo "observability-up: Prometheus http://127.0.0.1:${PROM_PORT}"
echo "observability-up: OTLP gRPC 127.0.0.1:${OTLP_PORT} (set OTEL_EXPORTER_OTLP_ENDPOINT=127.0.0.1:${OTLP_PORT})"
