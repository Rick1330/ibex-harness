#!/usr/bin/env bash
# Source this file before test commands to prevent sandbox/platform telemetry from
# changing local test behavior. Set IBEX_ALLOW_EXTERNAL_OTEL=1 to opt out.
if [[ "${IBEX_ALLOW_EXTERNAL_OTEL:-0}" != 1 ]]; then
  while IFS='=' read -r name _; do
    case "$name" in
      OTEL_*) unset "$name" ;;
      *) : ;;
    esac
  done < <(env)
fi
