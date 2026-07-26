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
SEED_ORG_ID="00000000-0000-0000-0000-000000000001"
SEED_AGENT_ID="00000000-0000-0000-0000-000000000003"
SEED_TOKEN_ID="00000000-0000-0000-0000-000000000004"

normalize_psql_dsn() {
  local dsn="$1"
  dsn="${dsn//postgresql+asyncpg:/postgres:}"
  dsn="${dsn//postgresql:/postgres:}"
  echo "$dsn"
}

run_psql_query() {
  local sql="$1"
  local dsn
  dsn="$(normalize_psql_dsn "$POSTGRES_DSN")"
  if command -v psql >/dev/null 2>&1; then
    psql "$dsn" -v ON_ERROR_STOP=1 -Atc "$sql"
    return
  fi
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ibex-dev-postgres; then
    docker exec -i ibex-dev-postgres \
      psql -U "${POSTGRES_USER:-ibex}" -d "${POSTGRES_DB:-ibex}" -v ON_ERROR_STOP=1 -Atc "$sql"
    return
  fi
  echo "benchmark seed check requires psql on PATH or running ibex-dev-postgres" >&2
  exit 1
}

verify_bench_seed() {
  local count
  count="$(run_psql_query "
SELECT COUNT(*) FROM ibex_core.organizations o
JOIN ibex_core.agents a ON a.org_id = o.id AND a.id = '${SEED_AGENT_ID}'
JOIN ibex_core.tokens t ON t.org_id = o.id AND t.id = '${SEED_TOKEN_ID}'
WHERE o.id = '${SEED_ORG_ID}';")"
  if [[ "${count//[[:space:]]/}" != "1" ]]; then
    echo "benchmark DB is not seeded (org/agent/PAT missing)." >&2
    echo "Run without BENCH_SKIP_SEED=1, or seed first (make db-seed)." >&2
    exit 1
  fi
}

if [[ "${BENCH_SKIP_SEED:-0}" != "1" ]]; then
  echo "seeding benchmark database..."
  bash "$ROOT_DIR/infra/scripts/db-seed.sh"
else
  echo "BENCH_SKIP_SEED=1: verifying pre-seeded org/agent/PAT..."
  verify_bench_seed
fi

write_env_kv() {
  local key="$1"
  local val="$2"
  local file="$3"
  if [[ "$val" == *$'\n'* || "$val" == *$'\r'* ]]; then
    echo "refusing newline in $key for env file" >&2
    exit 1
  fi
  # KEY=value lines for docker --env-file / dotenv consumers (no shell sourcing).
  printf '%s=%s\n' "$key" "$val" >>"$file"
}

mkdir -p "$ROOT_DIR/benchmarks/output"
umask 077
BENCH_PROXY_ENV_FILE="$(mktemp "$ROOT_DIR/benchmarks/output/bench-proxy.env.XXXXXX")"
: >"$BENCH_PROXY_ENV_FILE"
write_env_kv "IBEX_DEV_TOKEN" "$IBEX_DEV_TOKEN" "$BENCH_PROXY_ENV_FILE"
write_env_kv "IBEX_DEV_AGENT_ID" "$IBEX_DEV_AGENT_ID" "$BENCH_PROXY_ENV_FILE"
write_env_kv "IBEX_LLM_MODE" "$IBEX_LLM_MODE" "$BENCH_PROXY_ENV_FILE"
printf '%s\n' "$BENCH_PROXY_ENV_FILE" >"$ROOT_DIR/benchmarks/output/bench-proxy.env.path"
export BENCH_PROXY_ENV_FILE

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
    echo "bench env file: ${BENCH_PROXY_ENV_FILE}"
    exit 0
  fi
  sleep 0.5
done

echo "proxy stack failed to become ready" >&2
tail -n 50 /tmp/bench-auth.log >&2 || true
tail -n 50 /tmp/bench-proxy.log >&2 || true
exit 1
