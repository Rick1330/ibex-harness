#!/usr/bin/env bash
# Stop local LGTM observability stack.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BRIDGE_COMPOSE="$ROOT_DIR/infra/compose/observability/docker-compose.yml"
HOST_COMPOSE="$ROOT_DIR/infra/compose/overlays/host/observability.yml"
ENV_FILE="$ROOT_DIR/infra/compose/observability/.env"
ENV_EXAMPLE="$ROOT_DIR/infra/compose/observability/.env.example"
[[ -f "$ENV_FILE" ]] || ENV_FILE="$ENV_EXAMPLE"

runtime="${IBEX_RUNTIME:-auto}"
network="${IBEX_NETWORK:-bridge}"
if [[ "$runtime" == auto ]]; then
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then runtime=docker
  elif command -v podman >/dev/null 2>&1 && (podman compose version >/dev/null 2>&1 || command -v podman-compose >/dev/null 2>&1); then runtime=podman
  else echo 'observability-down: no supported Docker or Podman compose runtime found.' >&2; exit 1; fi
fi
case "$runtime" in
  docker) compose_cmd() { docker compose "$@"; } ;;
  podman)
    podman_bin=(podman)
    if [[ "${IBEX_PODMAN_SUDO:-0}" == 1 ]] || {
      [[ "$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)" == true ]] &&
      sudo -n podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null | grep -qx false
    }; then
      podman_bin=(sudo -n podman)
    fi
    if "${podman_bin[@]}" compose version >/dev/null 2>&1; then compose_cmd() { "${podman_bin[@]}" compose "$@"; }
    elif command -v podman-compose >/dev/null 2>&1; then compose_cmd() { podman-compose "$@"; }
    else echo 'observability-down: Podman Compose is unavailable.' >&2; exit 1; fi
    ;;
  *) echo "observability-down: unsupported runtime $runtime" >&2; exit 2 ;;
esac
if [[ "$network" == host ]]; then
  [[ "$runtime" == podman ]] || { echo 'observability-down: IBEX_NETWORK=host requires IBEX_RUNTIME=podman.' >&2; exit 2; }
  compose_args=(-p ibex-observability -f "$HOST_COMPOSE" --env-file "$ENV_FILE")
elif [[ "$network" == bridge ]]; then
  compose_args=(-f "$BRIDGE_COMPOSE" --env-file "$ENV_FILE")
else
  echo 'observability-down: IBEX_NETWORK must be bridge or host.' >&2
  exit 2
fi
compose_cmd "${compose_args[@]}" down
echo 'observability-down: stack stopped'
