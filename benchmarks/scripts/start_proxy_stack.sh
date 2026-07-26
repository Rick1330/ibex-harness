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
export IBEX_LLM_MODE="${IBEX_LLM_MODE:-mock}"

# Dev seed PAT + agent for k6 chat path (IBEX_LLM_MODE=mock → 200).
export IBEX_DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
export IBEX_DEV_AGENT_ID="${IBEX_DEV_AGENT_ID:-00000000-0000-0000-0000-000000000003}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "${BENCH_SKIP_SEED:-0}" != "1" ]]; then
  echo "seeding benchmark database..."
  bash "$ROOT_DIR/infra/scripts/db-seed.sh"
fi

# Persist token/agent for the k6 step (sourced by workflow env or docker -e).
cat > /tmp/bench-proxy.env <<EOF
IBEX_DEV_TOKEN=${IBEX_DEV_TOKEN}
IBEX_DEV_AGENT_ID=${IBEX_DEV_AGENT_ID}
IBEX_LLM_MODE=${IBEX_LLM_MODE}
EOF

go run ./services/auth/cmd/auth >/tmp/bench-auth.log 2>&1 &
echo $! >/tmp/bench-auth.pid

export IBEX_PORT="${BENCH_PROXY_PORT}"
export IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}"
export REDIS_URL

go run ./services/proxy/cmd/proxy >/tmp/bench-proxy.log 2>&1 &
echo $! >/tmp/bench-proxy.pid

echo "starting auth and proxy (go run compile may take ~20-40s on CI)..."

for attempt in $(seq 1 90); do
  if curl -fsS --max-time 1 "http://127.0.0.1:${BENCH_PROXY_PORT}/health" >/dev/null 2>/dev/null; then
    echo "proxy ready on http://127.0.0.1:${BENCH_PROXY_PORT}/health (attempt ${attempt})"
    exit 0
  fi
  sleep 0.5
done

echo "proxy stack failed to become ready" >&2
tail -n 50 /tmp/bench-auth.log >&2 || true
tail -n 50 /tmp/bench-proxy.log >&2 || true
exit 1
