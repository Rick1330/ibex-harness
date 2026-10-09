#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/infra/tool-versions.conf"

runtime="${IBEX_RUNTIME:-auto}"
network="${IBEX_NETWORK:-bridge}"
os_name="$(uname -s)"
arch="$(uname -m)"
shell_name="${SHELL:-unknown}"

if [[ "$runtime" == auto ]]; then
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then runtime=docker
  elif command -v podman >/dev/null 2>&1 && (podman compose version >/dev/null 2>&1 || command -v podman-compose >/dev/null 2>&1); then runtime=podman
  else runtime=unavailable
  fi
fi

printf 'IBEX environment doctor\n'
printf '  OS/arch: %s/%s\n' "$os_name" "$arch"
printf '  shell: %s\n' "$shell_name"
printf '  runtime: %s\n' "$runtime"
printf '  network: %s\n' "$network"

if [[ "$runtime" == unavailable ]]; then
  echo '  diagnosis: no Docker Compose or Podman Compose runtime found' >&2
else
  echo "  diagnosis: runtime detected; compose commands will use $runtime"
fi

otel_found=0
while IFS='=' read -r name _; do
  if [[ "$name" == OTEL_* && -n "${!name:-}" ]]; then
    [[ $otel_found -eq 0 ]] && echo '  injected OTEL_* variables:'
    printf '    %s=<set>\n' "$name"
    otel_found=1
  fi
done < <(env)
[[ $otel_found -eq 0 ]] && echo '  injected OTEL_* variables: none'

printf '  localhost: '
if getent hosts localhost >/dev/null 2>&1; then echo 'resolves'
else echo 'does not resolve'; fi

ports=(5432 5433 6379 6380 8123 8124 9000 9002 9001 9100 9101 19090 3000 3200 3100 4317 4318 13133 9093)
printf '  port availability:\n'
for port in "${ports[@]}"; do
  if (echo >/dev/tcp/127.0.0.1/$port) >/dev/null 2>&1; then
    printf '    %-5s in-use\n' "$port"
  else
    printf '    %-5s available\n' "$port"
  fi
done

if [[ "$network" == host ]]; then
  echo '  host-network note: Compose service DNS and host-gateway aliases are unavailable; configs must use 127.0.0.1.'
fi
if [[ "$otel_found" -eq 1 && "${IBEX_ALLOW_EXTERNAL_OTEL:-0}" != 1 ]]; then
  echo '  telemetry note: test commands will unset external OTEL_* variables unless IBEX_ALLOW_EXTERNAL_OTEL=1.'
fi
