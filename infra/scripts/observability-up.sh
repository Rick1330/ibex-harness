#!/usr/bin/env bash
# Start local LGTM observability stack (ADR-0051).
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BRIDGE_COMPOSE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
HOST_COMPOSE="$ROOT_DIR/infra/compose/overlays/host/observability.yml"
ENV_FILE="$ROOT_DIR/infra/compose/observability/.env"
ENV_EXAMPLE="$ROOT_DIR/infra/compose/observability/.env.example"
SECRETS_DIR="$ROOT_DIR/infra/monitoring/prometheus/scrape-auth"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "observability-up: created $ENV_FILE from .env.example"
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

runtime="${IBEX_RUNTIME:-auto}"
network="${IBEX_NETWORK:-bridge}"
if [[ "$runtime" == auto ]]; then
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    runtime=docker
  elif command -v podman >/dev/null 2>&1 && (podman compose version >/dev/null 2>&1 || command -v podman-compose >/dev/null 2>&1); then
    runtime=podman
  else
    echo 'observability-up: no supported Docker or Podman compose runtime found.' >&2
    exit 1
  fi
fi

case "$runtime" in
  docker)
    command -v docker >/dev/null 2>&1 || { echo 'observability-up: Docker CLI is missing.' >&2; exit 1; }
    docker compose version >/dev/null 2>&1 || { echo 'observability-up: Docker Compose v2 is unavailable.' >&2; exit 1; }
    compose_cmd() { docker compose "$@"; }
    ;;
  podman)
    command -v podman >/dev/null 2>&1 || { echo 'observability-up: Podman is missing.' >&2; exit 1; }
    podman_bin=(podman)
    if [[ "${IBEX_PODMAN_SUDO:-0}" == 1 ]] || {
      [[ "$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)" == true ]] &&
      sudo -n podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null | grep -qx false
    }; then
      podman_bin=(sudo -n podman)
    fi
    if "${podman_bin[@]}" compose version >/dev/null 2>&1; then
      compose_cmd() { "${podman_bin[@]}" compose "$@"; }
    elif command -v podman-compose >/dev/null 2>&1; then
      compose_cmd() { podman-compose "$@"; }
    else
      echo 'observability-up: Podman Compose is unavailable.' >&2
      exit 1
    fi
    ;;
  *) echo "observability-up: IBEX_RUNTIME must be docker, podman, or auto (got $runtime)." >&2; exit 2 ;;
esac

if [[ "$network" == host ]]; then
  [[ "$runtime" == podman ]] || { echo 'observability-up: IBEX_NETWORK=host requires IBEX_RUNTIME=podman.' >&2; exit 2; }
  compose_args=(-p ibex-observability -f "$HOST_COMPOSE" --env-file "$ENV_FILE")
elif [[ "$network" == bridge ]]; then
  compose_args=(-f "$BRIDGE_COMPOSE" --env-file "$ENV_FILE")
else
  echo 'observability-up: IBEX_NETWORK must be bridge or host.' >&2
  exit 2
fi

mkdir -p "$SECRETS_DIR"
umask 077
printf '%s' "${IBEX_EMBEDDING_METRICS_BEARER:-dev-embedder-metrics-token}" \
  >"$SECRETS_DIR/embedder_metrics_bearer"
compose_cmd "${compose_args[@]}" up -d

if [[ "$network" == host ]]; then
  grafana_port=3000
  prom_port=9090
  otlp_port=4317
else
  grafana_port="${IBEX_OBS_GRAFANA_PORT:-3000}"
  prom_port="${IBEX_OBS_PROMETHEUS_PORT:-9090}"
  otlp_port="${IBEX_OBS_OTLP_GRPC_PORT:-4317}"
fi
echo "observability-up: runtime=$runtime network=$network"
echo "observability-up: Grafana http://127.0.0.1:${grafana_port} (loopback; anonymous Viewer)"
echo "observability-up: Prometheus http://127.0.0.1:${prom_port}"
echo "observability-up: OTLP gRPC 127.0.0.1:${otlp_port} (set OTEL_EXPORTER_OTLP_ENDPOINT=127.0.0.1:${otlp_port})"
