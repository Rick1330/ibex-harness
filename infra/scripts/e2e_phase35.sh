#!/usr/bin/env bash
# Phase 3.5 learning-loop e2e (3.5.F.1): terminate → extract → memory → inject,
# plus cross-tenant smoke, latency mechanism, degradation ladder, MCP/proxy.
#
# Modes:
#   IBEX_E2E_P35_MANAGE=1 (default) — start/stop auth, embedder, memory, worker,
#     context, proxy, mcp-memory, extraction stub
#   IBEX_E2E_P35_MANAGE=0 — use already-running services on configured ports
#
# Prerequisites (manage mode): make compose-test-up && make db-migrate && make db-seed
# Exit criterion #9: make e2e-smoke-p3.5 → this script.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Avoid a caller-activated venv steering uv sync/pip into the wrong project.
unset VIRTUAL_ENV
cd "$ROOT_DIR"

PROXY_ADDR="${IBEX_PROXY_ADDR:-http://127.0.0.1:18080}"
AUTH_HTTP="${IBEX_AUTH_HTTP:-http://127.0.0.1:18081}"
AUTH_GRPC_PORT="${IBEX_GRPC_PORT:-19091}"
STUB_TEI_PORT="${IBEX_E2E_STUB_TEI_PORT:-18083}"
EMBEDDER_ADDR="${IBEX_EMBEDDER_ADDR:-http://127.0.0.1:18004}"
MEMORY_ADDR="${IBEX_MEMORY_ADDR:-http://127.0.0.1:8005}"
MCP_ADDR="${IBEX_MCP_ADDR:-http://127.0.0.1:18090}"
CONTEXT_GRPC_ADDR="${IBEX_CONTEXT_GRPC_ADDR:-127.0.0.1:9092}"
EXTRACTION_STUB_PORT="${IBEX_E2E_P35_EXTRACTION_STUB_PORT:-18091}"
WORKER_ENQUEUE_PORT="${IBEX_WORKER_ENQUEUE_PORT:-8007}"
WORKER_METRICS_PORT="${IBEX_WORKER_METRICS_PORT:-8006}"
ENQUEUE_TOKEN="${IBEX_WORKER_ENQUEUE_API_TOKEN:-dev-enqueue-token}"
DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
DEV_ORG="${IBEX_DEV_ORG_ID:-00000000-0000-0000-0000-000000000001}"
DEV_AGENT="${IBEX_DEV_AGENT_ID:-00000000-0000-0000-0000-000000000003}"
ORG_B="${IBEX_E2E_P35_ORG_B:-00000000-0000-0000-0000-0000000000b1}"
USER_B="${IBEX_E2E_P35_USER_B:-00000000-0000-0000-0000-0000000000b2}"
AGENT_B="${IBEX_E2E_P35_AGENT_B:-00000000-0000-0000-0000-0000000000b3}"
TOKEN_B="${IBEX_E2E_P35_TOKEN_B:-ibex_pat_00000000-0000-0000-0000-0000000000b4_LOCALDEVELOPMENTONLY}"
# Argon2id hash for TOKEN_B (infra/tools/hashtoken).
TOKEN_B_HASH='$argon2id$v=19$m=65536,t=3,p=4$6x+E2VCaFwBH2tFrH3LHrg$70eZtxRKlYlPKFLyMNpsTWpOiDzxVJaHXIg284LNz84'
TOKEN_B_PREFIX='ibex_pat_00000000-0000-0000-0000-0000000000b4'
EMBED_TOKEN="${IBEX_EMBEDDING_API_TOKEN:-dev-embedder-metrics-token}"
MANAGE="${IBEX_E2E_P35_MANAGE:-1}"
LOG_DIR="${IBEX_E2E_P35_LOG_DIR:-/tmp/ibex-e2e-phase35}"
LIVE_EXTRACTION="${IBEX_E2E_P35_LIVE_EXTRACTION:-0}"
STUB_TEI_PY="$ROOT_DIR/infra/scripts/phase3_e2e_stub_tei.py"
EXTRACTION_STUB_PY="$ROOT_DIR/infra/scripts/phase35_e2e_extraction_stub.py"
SAFE_MARKER_PY="$ROOT_DIR/infra/scripts/phase35_e2e_safe_marker.py"
SCENARIOS_PY="$ROOT_DIR/infra/scripts/e2e_phase35_scenarios.py"
MEMORY_DIR="$ROOT_DIR/services/memory"
EMBEDDER_DIR="$ROOT_DIR/services/embedder"
WORKER_DIR="$ROOT_DIR/services/worker"
CONTEXT_DIR="$ROOT_DIR/services/context"
MCP_DIR="$ROOT_DIR/services/mcp-memory"
PORT_FROM_URL_SED='s#.*:([0-9]+).*#\1#'
DOCKER_PS_FORMAT='{{.Names}}'
PSQL_PING='SELECT 1'

PIDS=()
CONTEXT_PID=""
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

MARKER="${IBEX_E2E_P35_MARKER:-}"
if [[ -z "$MARKER" ]]; then
  # Presidio false-positives on hex/NATO concatenations; sample+verify via memory PII.
  MARKER="$(cd "$MEMORY_DIR" && uv run python "$SAFE_MARKER_PY")" \
    || fail "failed to generate Presidio-clean IBEX_E2E_P35_MARKER"
fi
MCP_MARKER="${IBEX_E2E_P35_MCP_MARKER:-}"
if [[ -z "$MCP_MARKER" ]]; then
  for _ in 1 2 3 4 5 6 7 8; do
    MCP_MARKER="$(cd "$MEMORY_DIR" && uv run python "$SAFE_MARKER_PY")" \
      || fail "failed to generate Presidio-clean IBEX_E2E_P35_MCP_MARKER"
    if [[ "$MCP_MARKER" != "$MARKER" ]]; then
      break
    fi
  done
fi

cleanup() {
  if [[ -n "${CONTEXT_PID:-}" ]] && kill -0 "$CONTEXT_PID" 2>/dev/null; then
    # Ensure context is not left stopped after scenario 5 SIGSTOP.
    kill -CONT "$CONTEXT_PID" 2>/dev/null || true
  fi
  if [[ "$MANAGE" != "1" ]]; then
    return 0
  fi
  local pid
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

wait_http() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-120}"
  for _ in $(seq 1 "$max_attempts"); do
    if curl -fsS --connect-timeout 1 --max-time 3 "$url" >/dev/null 2>&1; then
      pass "$name ready ($url)"
      return 0
    fi
    sleep 0.5
  done
  fail "$name not ready: $url"
}

wait_tcp() {
  local name="$1"
  local hostport="$2"
  local max_attempts="${3:-120}"
  local host="${hostport%%:*}"
  local port="${hostport##*:}"
  for _ in $(seq 1 "$max_attempts"); do
    if (echo >/dev/tcp/"$host"/"$port") >/dev/null 2>&1; then
      pass "$name ready ($hostport)"
      return 0
    fi
    sleep 0.5
  done
  fail "$name not ready: $hostport"
}

normalize_psql_dsn() {
  local dsn="$1"
  dsn="${dsn//postgresql+asyncpg:/postgres:}"
  dsn="${dsn//postgresql:/postgres:}"
  echo "$dsn"
}

run_psql() {
  local dsn
  dsn="$(normalize_psql_dsn "${POSTGRES_DSN}")"
  if command -v psql >/dev/null 2>&1; then
    psql "$dsn" -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx ibex-test-postgres; then
    docker exec -i ibex-test-postgres psql -U ibex -d ibex_test -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx test-postgres-1; then
    docker exec -i test-postgres-1 psql -U ibex -d ibex_test -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx ibex-dev-postgres; then
    docker exec -i ibex-dev-postgres psql -U ibex -d ibex -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  fail "psql not available"
}

postgres_preflight() {
  local dsn
  dsn="$(normalize_psql_dsn "${POSTGRES_DSN}")"
  if command -v psql >/dev/null 2>&1; then
    if psql "$dsn" -v ON_ERROR_STOP=1 -c "$PSQL_PING" >/dev/null 2>&1; then
      pass "postgres reachable ($dsn)"
      return 0
    fi
    fail "Postgres not reachable at POSTGRES_DSN"
  fi
  for container in ibex-test-postgres test-postgres-1 ibex-dev-postgres; do
    if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx "$container"; then
      local db=ibex_test
      if [[ "$container" == "ibex-dev-postgres" ]]; then
        db=ibex
      fi
      if docker exec "$container" psql -U ibex -d "$db" -c "$PSQL_PING" >/dev/null 2>&1; then
        pass "postgres reachable ($container)"
        return 0
      fi
    fi
  done
  fail "Postgres not reachable (make compose-test-up && make db-migrate)"
}

seed_org_b() {
  run_psql <<SQL
SELECT set_config('app.is_service_account', 'true', true);

INSERT INTO ibex_core.organizations (id, name, slug, tier, status)
VALUES (
  '${ORG_B}'::uuid, 'IBEX E2E Org B', 'ibex-e2e-b', 'free', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.users (id, org_id, email, name, role, status)
VALUES (
  '${USER_B}'::uuid, '${ORG_B}'::uuid, 'e2e-b@ibex.local', 'E2E User B', 'owner', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
VALUES (
  '${AGENT_B}'::uuid, '${ORG_B}'::uuid, '${USER_B}'::uuid,
  'E2E Agent B', 'e2e-agent-b', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.tokens (
  id, org_id, user_id, agent_id, type, hash, prefix, name, permissions, is_revoked
) VALUES (
  '00000000-0000-0000-0000-0000000000b4'::uuid,
  '${ORG_B}'::uuid,
  '${USER_B}'::uuid,
  '${AGENT_B}'::uuid,
  'pat',
  '${TOKEN_B_HASH}',
  '${TOKEN_B_PREFIX}',
  'E2E Org B Seed Token',
  270633733891,
  false
) ON CONFLICT (id) DO NOTHING;
SQL
  pass "seeded Org B user/agent/token"
}

start_stack() {
  mkdir -p "$LOG_DIR"
  export IBEX_ENV=development
  export POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable}"
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/0}"
  export IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}"
  export IBEX_LLM_MODE="${IBEX_LLM_MODE:-mock}"
  unset CLICKHOUSE_DSN || true
  unset OTEL_EXPORTER_OTLP_ENDPOINT || true

  local proxy_port auth_http_port embedder_port memory_port mcp_port
  proxy_port="$(echo "$PROXY_ADDR" | sed -E "$PORT_FROM_URL_SED")"
  auth_http_port="$(echo "$AUTH_HTTP" | sed -E "$PORT_FROM_URL_SED")"
  embedder_port="$(echo "$EMBEDDER_ADDR" | sed -E "$PORT_FROM_URL_SED")"
  memory_port="$(echo "$MEMORY_ADDR" | sed -E "$PORT_FROM_URL_SED")"
  mcp_port="$(echo "$MCP_ADDR" | sed -E "$PORT_FROM_URL_SED")"

  # Build auth/proxy binaries so PIDS track the process holding the port
  # (go run's wrapper PID is not the listener — cleanup would leak ports).
  local auth_bin proxy_bin
  auth_bin="$LOG_DIR/ibex-auth"
  proxy_bin="$LOG_DIR/ibex-proxy"
  echo "e2e-phase35: building auth → ${auth_bin}..."
  go build -o "$auth_bin" ./services/auth/cmd/auth
  echo "e2e-phase35: building proxy → ${proxy_bin}..."
  go build -o "$proxy_bin" ./services/proxy/cmd/proxy

  echo "e2e-phase35: starting auth on :${auth_http_port}/:${AUTH_GRPC_PORT}..."
  IBEX_PORT="$auth_http_port" IBEX_GRPC_PORT="$AUTH_GRPC_PORT" OTEL_SERVICE_NAME=ibex-auth \
    "$auth_bin" >"$LOG_DIR/auth.log" 2>&1 &
  PIDS+=("$!")
  wait_http "auth" "$AUTH_HTTP/health"

  echo "e2e-phase35: starting stub TEI on :${STUB_TEI_PORT}..."
  (
    cd "$EMBEDDER_DIR"
    if [[ ! -d .venv ]]; then
      # Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
      uv sync --frozen --no-build >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    # Child-only env via `env` (not `export`) — avoids Codacy/ShellCheck SC2030/SC2031.
    exec env PYTHONPATH="$EMBEDDER_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python "$STUB_TEI_PY" --host 127.0.0.1 --port "$STUB_TEI_PORT"
  ) >"$LOG_DIR/stub-tei.log" 2>&1 &
  PIDS+=("$!")
  wait_http "stub-tei" "http://127.0.0.1:${STUB_TEI_PORT}/health"

  echo "e2e-phase35: starting embedder on :${embedder_port}..."
  (
    cd "$EMBEDDER_DIR"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec env \
      IBEX_EMBEDDING_PROFILE=gpu \
      IBEX_EMBEDDING_TEI_BASE_URL="http://127.0.0.1:${STUB_TEI_PORT}" \
      IBEX_EMBEDDING_TEI_ALLOW_INSECURE=true \
      IBEX_EMBEDDING_DIM=1024 \
      IBEX_EMBEDDING_MODEL=BAAI/bge-m3 \
      IBEX_EMBEDDING_API_TOKEN="$EMBED_TOKEN" \
      IBEX_EMBEDDING_CACHE_ENABLED=false \
      uvicorn app.main:app --host 127.0.0.1 --port "$embedder_port"
  ) >"$LOG_DIR/embedder.log" 2>&1 &
  PIDS+=("$!")
  wait_http "embedder" "$EMBEDDER_ADDR/health"

  echo "e2e-phase35: starting memory on :${memory_port}..."
  (
    cd "$MEMORY_DIR"
    if [[ ! -d .venv ]]; then
      bash "$ROOT_DIR/infra/scripts/memory-uv-sync.sh" >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec env \
      IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}" \
      IBEX_MEMORY_AUTH_TIMEOUT_MS="${IBEX_MEMORY_AUTH_TIMEOUT_MS:-2000}" \
      IBEX_MEMORY_EMBEDDING_BASE_URL="$EMBEDDER_ADDR" \
      IBEX_EMBEDDING_API_TOKEN="$EMBED_TOKEN" \
      IBEX_MEMORY_DATABASE_URL="${POSTGRES_DSN}" \
      IBEX_MEMORY_REDIS_URL="${REDIS_URL}" \
      uvicorn app.main:app --host 127.0.0.1 --port "$memory_port"
  ) >"$LOG_DIR/memory.log" 2>&1 &
  PIDS+=("$!")
  wait_http "memory" "$MEMORY_ADDR/health" 180
  wait_http "memory" "$MEMORY_ADDR/ready" 180

  if [[ "$LIVE_EXTRACTION" == "1" ]]; then
    echo "e2e-phase35: LIVE extraction — skipping stub; using OpenRouter/OpenAI-compat from env"
    [[ -n "${OPENAI_API_KEY:-}" ]] || fail "IBEX_E2E_P35_LIVE_EXTRACTION=1 requires OPENAI_API_KEY"
    [[ -n "${IBEX_WORKER_EXTRACTION_OPENAI_BASE_URL:-}" ]] \
      || fail "IBEX_E2E_P35_LIVE_EXTRACTION=1 requires IBEX_WORKER_EXTRACTION_OPENAI_BASE_URL"
    [[ -n "${IBEX_WORKER_EXTRACTION_OPENAI_MODEL:-}" ]] \
      || fail "IBEX_E2E_P35_LIVE_EXTRACTION=1 requires IBEX_WORKER_EXTRACTION_OPENAI_MODEL"
  else
    echo "e2e-phase35: starting extraction stub on :${EXTRACTION_STUB_PORT}..."
    IBEX_E2E_P35_MARKER="$MARKER" \
      python3 "$EXTRACTION_STUB_PY" --host 127.0.0.1 --port "$EXTRACTION_STUB_PORT" --marker "$MARKER" \
      >"$LOG_DIR/extraction-stub.log" 2>&1 &
    PIDS+=("$!")
    wait_http "extraction-stub" "http://127.0.0.1:${EXTRACTION_STUB_PORT}/health"
  fi

  echo "e2e-phase35: starting worker (celery + enqueue :${WORKER_ENQUEUE_PORT})..."
  local worker_openai_base worker_openai_key worker_timeout_args=()
  if [[ "$LIVE_EXTRACTION" == "1" ]]; then
    worker_openai_base="${IBEX_WORKER_EXTRACTION_OPENAI_BASE_URL}"
    # Live extraction sends OPENAI_API_KEY to a remote LLM — require HTTPS.
    [[ "$worker_openai_base" == https://* ]] \
      || fail "IBEX_WORKER_EXTRACTION_OPENAI_BASE_URL must use https:// (refusing non-HTTPS live endpoint)"
    worker_openai_key="${OPENAI_API_KEY}"
    worker_timeout_args=(
      IBEX_WORKER_EXTRACTION_OPENAI_MODEL="${IBEX_WORKER_EXTRACTION_OPENAI_MODEL}"
      IBEX_WORKER_EXTRACTION_TIMEOUT_SECONDS="${IBEX_WORKER_EXTRACTION_TIMEOUT_SECONDS:-120}"
    )
  else
    worker_openai_base="http://127.0.0.1:${EXTRACTION_STUB_PORT}/v1"
    worker_openai_key="sk-e2e-phase35-not-real"
  fi
  (
    cd "$WORKER_DIR"
    if [[ ! -d .venv ]]; then
      bash "$ROOT_DIR/infra/scripts/worker-uv-sync.sh" >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec env -u CLICKHOUSE_DSN \
      REDIS_URL="$REDIS_URL" \
      REDIS_DB_QUEUE=1 \
      REDIS_DB_RESULTS=3 \
      POSTGRES_DSN="$POSTGRES_DSN" \
      IBEX_WORKER_METRICS_PORT="$WORKER_METRICS_PORT" \
      IBEX_WORKER_ENQUEUE_PORT="$WORKER_ENQUEUE_PORT" \
      IBEX_WORKER_ENQUEUE_HOST=127.0.0.1 \
      IBEX_WORKER_ENQUEUE_API_TOKEN="$ENQUEUE_TOKEN" \
      IBEX_WORKER_EXTRACTION_PROVIDER="${IBEX_WORKER_EXTRACTION_PROVIDER:-openai}" \
      IBEX_WORKER_EXTRACTION_OPENAI_BASE_URL="$worker_openai_base" \
      OPENAI_API_KEY="$worker_openai_key" \
      "${worker_timeout_args[@]}" \
      IBEX_WORKER_MEMORY_BASE_URL="$MEMORY_ADDR" \
      IBEX_WORKER_MEMORY_API_TOKEN="$DEV_TOKEN" \
      celery -A app.celery_app:celery_app worker \
      -n "ibex-e2e-p35@%h" \
      -Q extraction,embedding,maintenance,mcp_audit \
      --loglevel=info \
      --concurrency=2
  ) >"$LOG_DIR/worker.log" 2>&1 &
  PIDS+=("$!")
  wait_http "worker-enqueue" "http://127.0.0.1:${WORKER_ENQUEUE_PORT}/health" 180

  echo "e2e-phase35: starting context gRPC on ${CONTEXT_GRPC_ADDR}..."
  bash "$ROOT_DIR/infra/scripts/context-proto-gen.sh" >/dev/null
  local context_pythonpath="$ROOT_DIR/packages/proto/gen/python${PYTHONPATH:+:$PYTHONPATH}"
  (
    cd "$CONTEXT_DIR"
    if [[ ! -d .venv ]]; then
      bash "$ROOT_DIR/infra/scripts/context-uv-sync.sh" >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    # Generous process-managed budgets: local/CI hosts often exceed 80–200ms
    # memory HTTP RTT under cold start; too-tight walls force L2 timeouts and
    # greenwash inject/L0–L1 proofs (candidates=0).
    exec env \
      PYTHONPATH="$context_pythonpath" \
      IBEX_CONTEXT_GRPC_ADDR="$CONTEXT_GRPC_ADDR" \
      IBEX_CONTEXT_MEMORY_BASE_URL="$MEMORY_ADDR" \
      IBEX_CONTEXT_MEMORY_API_TOKEN="$DEV_TOKEN" \
      IBEX_CONTEXT_REDIS_URL="$REDIS_URL" \
      IBEX_CONTEXT_TIMEOUT=2s \
      IBEX_CONTEXT_DEADLINE_MS=1500 \
      IBEX_CONTEXT_HOT_TIMEOUT_MS=800 \
      IBEX_CONTEXT_COLD_TIMEOUT_MS=1200 \
      python -m app
  ) >"$LOG_DIR/context.log" 2>&1 &
  CONTEXT_PID="$!"
  PIDS+=("$CONTEXT_PID")
  wait_tcp "context" "$CONTEXT_GRPC_ADDR" 180

  echo "e2e-phase35: starting proxy on :${proxy_port}..."
  # Prefix env on the command (no subshell exports) for Codacy SC2030/SC2031.
  IBEX_PORT="$proxy_port" \
    IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}" \
    POSTGRES_DSN="$POSTGRES_DSN" \
    REDIS_URL="$REDIS_URL" \
    IBEX_LLM_MODE=mock \
    IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}" \
    IBEX_RATE_LIMIT_DEFAULT_RPM="${IBEX_RATE_LIMIT_DEFAULT_RPM:-6000}" \
    IBEX_CONTEXT_ENABLED=true \
    IBEX_CONTEXT_GRPC_TARGET="$CONTEXT_GRPC_ADDR" \
    IBEX_CONTEXT_ASSEMBLE_TIMEOUT=2s \
    IBEX_CONTEXT_EMBED_METADATA=true \
    IBEX_WORKER_ENQUEUE_BASE_URL="http://127.0.0.1:${WORKER_ENQUEUE_PORT}" \
    IBEX_WORKER_ENQUEUE_API_TOKEN="$ENQUEUE_TOKEN" \
    OTEL_SERVICE_NAME=ibex-proxy \
    "$proxy_bin" \
    >"$LOG_DIR/proxy.log" 2>&1 &
  PIDS+=("$!")
  wait_http "proxy" "$PROXY_ADDR/health"

  echo "e2e-phase35: starting mcp-memory on :${mcp_port}..."
  (
    cd "$MCP_DIR"
    if [[ ! -d .venv ]]; then
      # Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
      uv sync --frozen --no-build --extra dev >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec env -u IBEX_MCP_CLICKHOUSE_URL -u IBEX_MCP_REDIS_URL \
      IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}" \
      IBEX_MCP_AUTH_TIMEOUT_MS="${IBEX_MCP_AUTH_TIMEOUT_MS:-2000}" \
      IBEX_MCP_HOST=127.0.0.1 \
      IBEX_MCP_PORT="$mcp_port" \
      IBEX_MCP_RESOURCE_URL="http://127.0.0.1:${mcp_port}/mcp" \
      IBEX_MCP_AUTH_SERVER_URL="http://127.0.0.1:${proxy_port}" \
      IBEX_MEMORY_HTTP_URL="$MEMORY_ADDR" \
      IBEX_MCP_MEMORY_HTTP_URL="$MEMORY_ADDR" \
      uvicorn app.main:app --host 127.0.0.1 --port "$mcp_port"
  ) >"$LOG_DIR/mcp.log" 2>&1 &
  PIDS+=("$!")
  wait_http "mcp" "$MCP_ADDR/health"
}

echo "=== Phase 3.5 learning-loop e2e (3.5.F.1) ==="
echo "  manage=$MANAGE live_extraction=$LIVE_EXTRACTION logs=$LOG_DIR marker=$MARKER mcp_marker=$MCP_MARKER"
if [[ "$LIVE_EXTRACTION" == "1" ]]; then
  export IBEX_E2E_P35_EVENTUALLY_TIMEOUT="${IBEX_E2E_P35_EVENTUALLY_TIMEOUT:-180}"
fi

export POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/0}"

if [[ "$MANAGE" == "1" ]]; then
  postgres_preflight
  bash "$ROOT_DIR/infra/scripts/db-seed.sh" >/dev/null
  seed_org_b
  bash "$ROOT_DIR/infra/scripts/memory-uv-sync.sh" >/dev/null
  bash "$ROOT_DIR/infra/scripts/embedder-uv-sync.sh" >/dev/null
  bash "$ROOT_DIR/infra/scripts/worker-uv-sync.sh" >/dev/null
  bash "$ROOT_DIR/infra/scripts/context-uv-sync.sh" >/dev/null
  start_stack
else
  wait_http "auth" "$AUTH_HTTP/health"
  wait_http "proxy" "$PROXY_ADDR/health"
  wait_http "memory" "$MEMORY_ADDR/health"
  wait_http "mcp" "$MCP_ADDR/health"
  wait_tcp "context" "$CONTEXT_GRPC_ADDR"
fi

CODE="$(curl -sS -o /dev/null -w '%{http_code}' "$PROXY_ADDR/ready" || true)"
[[ "$CODE" == "200" ]] || fail "proxy /ready -> $CODE"
pass "proxy /ready"

# Scenario driver uses memory venv (httpx) + proto stubs on PYTHONPATH.
# Child-scoped via function subshell — no `export` (Codacy SC2030/SC2031).
export IBEX_PROXY_ADDR="$PROXY_ADDR"
export IBEX_MEMORY_ADDR="$MEMORY_ADDR"
export IBEX_MCP_ADDR="$MCP_ADDR"
export IBEX_CONTEXT_GRPC_ADDR="$CONTEXT_GRPC_ADDR"
export IBEX_DEV_TOKEN="$DEV_TOKEN"
export IBEX_DEV_ORG_ID="$DEV_ORG"
export IBEX_DEV_AGENT_ID="$DEV_AGENT"
export IBEX_E2E_P35_ORG_B="$ORG_B"
export IBEX_E2E_P35_AGENT_B="$AGENT_B"
export IBEX_E2E_P35_TOKEN_B="$TOKEN_B"
export IBEX_E2E_P35_MARKER="$MARKER"
export IBEX_E2E_P35_MCP_MARKER="$MCP_MARKER"
export IBEX_E2E_P35_WORKER_LOG="$LOG_DIR/worker.log"
if [[ -n "${CONTEXT_PID:-}" ]]; then
  export IBEX_E2E_P35_CONTEXT_PID="$CONTEXT_PID"
fi

run_scenarios() (
  cd "$MEMORY_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  local py_path="$ROOT_DIR/packages/proto/gen/python${PYTHONPATH:+:$PYTHONPATH}"
  # memory venv may lack google.protobuf; context venv has grpc + protobuf + httpx.
  if ! PYTHONPATH="$py_path" python -c "import grpc; from ibex.context.v1 import context_pb2" 2>/dev/null; then
    # shellcheck disable=SC1091
    source "$CONTEXT_DIR/.venv/bin/activate"
  fi
  PYTHONPATH="$py_path" python -c "import grpc; from ibex.context.v1 import context_pb2; import httpx" \
    || fail "scenario driver needs grpc, context_pb2, and httpx"
  PYTHONPATH="$py_path" python "$SCENARIOS_PY"
)
run_scenarios

echo ""
echo "e2e-smoke-p3.5 passed"
