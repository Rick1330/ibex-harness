#!/usr/bin/env bash
set -euo pipefail

BENCH_PROXY_PORT="${BENCH_PROXY_PORT:-18082}"
AUTH_GRPC_PORT="${AUTH_GRPC_PORT:-9091}"
POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"

export IBEX_ENV=development
export IBEX_LOG_LEVEL=ERROR
export POSTGRES_DSN
export IBEX_GRPC_PORT="${AUTH_GRPC_PORT}"
export IBEX_PORT=18081

go run ./services/auth/cmd/auth >/tmp/bench-auth.log 2>&1 &
echo $! >/tmp/bench-auth.pid

export IBEX_PORT="${BENCH_PROXY_PORT}"
export IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}"
export REDIS_URL

go run ./services/proxy/cmd/proxy >/tmp/bench-proxy.log 2>&1 &
echo $! >/tmp/bench-proxy.pid

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${BENCH_PROXY_PORT}/health" >/dev/null; then
    echo "proxy ready on http://127.0.0.1:${BENCH_PROXY_PORT}/health"
    exit 0
  fi
  sleep 0.5
done

echo "proxy stack failed to become ready" >&2
tail -n 50 /tmp/bench-auth.log >&2 || true
tail -n 50 /tmp/bench-proxy.log >&2 || true
exit 1
