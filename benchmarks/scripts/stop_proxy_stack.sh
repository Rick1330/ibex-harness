#!/usr/bin/env bash
set -euo pipefail

for pid_file in /tmp/bench-proxy.pid /tmp/bench-auth.pid; do
  if [[ -f "${pid_file}" ]]; then
    kill "$(cat "${pid_file}")" 2>/dev/null || true
    rm -f "${pid_file}"
  fi
done
