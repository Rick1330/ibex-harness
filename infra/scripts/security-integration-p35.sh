#!/usr/bin/env bash
# 3.5.F.2 ISO-MCP-* security integration (auth + memory + Postgres).
# Starts auth + stub TEI + embedder + memory, seeds Org A/B + F.2 fixtures,
# runs pytest -m iso_mcp (mcp-memory 01..03 + worker 04). Min collect count = 4.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
unset VIRTUAL_ENV
cd "$ROOT"

CANONICAL_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-${IBEX_MEMORY_DATABASE_URL:-}}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "POSTGRES_DSN, POSTGRES_TEST_DSN, or IBEX_MEMORY_DATABASE_URL required" >&2
  exit 1
fi
if [[ -z "${REDIS_URL:-}" ]]; then
  echo "REDIS_URL required for security-integration-p3.5" >&2
  exit 1
fi

export POSTGRES_DSN="${CANONICAL_DSN}"
export POSTGRES_MIGRATE_DSN="${CANONICAL_DSN}"
export POSTGRES_TEST_DSN="${CANONICAL_DSN}"
export IBEX_MEMORY_DATABASE_URL="${CANONICAL_DSN}"
export IBEX_ENV="${IBEX_ENV:-development}"

AUTH_HTTP_PORT="${IBEX_ISO_MCP_AUTH_HTTP_PORT:-18181}"
AUTH_GRPC_PORT="${IBEX_ISO_MCP_AUTH_GRPC_PORT:-19191}"
STUB_TEI_PORT="${IBEX_ISO_MCP_STUB_TEI_PORT:-18183}"
EMBEDDER_PORT="${IBEX_ISO_MCP_EMBEDDER_PORT:-18104}"
MEMORY_PORT="${IBEX_ISO_MCP_MEMORY_PORT:-18105}"
LOG_DIR="${IBEX_ISO_MCP_LOG_DIR:-/tmp/ibex-security-p35}"
EMBED_TOKEN="${IBEX_EMBEDDING_API_TOKEN:-dev-embedder-metrics-token}"

ORG_A="00000000-0000-0000-0000-000000000001"
ORG_B="00000000-0000-0000-0000-0000000000b1"
USER_B="00000000-0000-0000-0000-0000000000b2"
AGENT_B="00000000-0000-0000-0000-0000000000b3"
TOKEN_B_HASH='$argon2id$v=19$m=65536,t=3,p=4$6x+E2VCaFwBH2tFrH3LHrg$70eZtxRKlYlPKFLyMNpsTWpOiDzxVJaHXIg284LNz84'
TOKEN_B_PREFIX='ibex_pat_00000000-0000-0000-0000-0000000000b4'

USER_A2="00000000-0000-0000-0000-0000000000c2"
AGENT_USER_B="00000000-0000-0000-0000-0000000000c3"
TOKEN_ORG_ID="00000000-0000-0000-0000-0000000000c4"
AGENT_SUSPENDED="00000000-0000-0000-0000-0000000000c5"
TOKEN_SUSPENDED_ID="00000000-0000-0000-0000-0000000000c6"

TOKEN_A="${IBEX_ISO_MCP_TOKEN_A:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
TOKEN_ORG="${IBEX_ISO_MCP_TOKEN_ORG_SCOPED:-ibex_pat_00000000-0000-0000-0000-0000000000f2_LOCALDEVELOPMENTONLY}"
TOKEN_SUSPENDED="${IBEX_ISO_MCP_TOKEN_SUSPENDED:-ibex_pat_00000000-0000-0000-0000-0000000000f3_LOCALDEVELOPMENTONLY}"
# Argon2id via: go run ./infra/tools/hashtoken <bearer>
TOKEN_ORG_HASH='$argon2id$v=19$m=65536,t=3,p=4$d1XID/KdLaepzl4fieO1Lw$XxWWKg6JtYCS5w/AJEheYxHLhCHb5kHaX8VfXx5FKtc'
TOKEN_ORG_PREFIX='ibex_pat_00000000-0000-0000-0000-0000000000f2'
TOKEN_SUSPENDED_HASH='$argon2id$v=19$m=65536,t=3,p=4$dkNEZlBzg2FQ3UO8HXX5PQ$cTFlLRLQBh3RG/uLhSHYzc2Sc69t+19AnHW3MRcnCeg'
TOKEN_SUSPENDED_PREFIX='ibex_pat_00000000-0000-0000-0000-0000000000f3'

MEMORY_DIR="$ROOT/services/memory"
EMBEDDER_DIR="$ROOT/services/embedder"
MCP_DIR="$ROOT/services/mcp-memory"
WORKER_DIR="$ROOT/services/worker"
STUB_TEI_PY="$ROOT/infra/scripts/phase3_e2e_stub_tei.py"
DOCKER_PS_FORMAT='{{.Names}}'

PIDS=()
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

cleanup() {
  local pid
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

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
  fail "psql not available"
}

wait_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      pass "$name ready ($url)"
      return 0
    fi
    sleep 1
  done
  fail "$name not ready: $url"
}

seed_stack() {
  bash "$ROOT/infra/scripts/db-seed.sh" >/dev/null
  run_psql <<SQL
SELECT set_config('app.is_service_account', 'true', true);

INSERT INTO ibex_core.organizations (id, name, slug, tier, status)
VALUES (
  '${ORG_B}'::uuid, 'IBEX ISO Org B', 'ibex-iso-b', 'free', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.users (id, org_id, email, name, role, status)
VALUES (
  '${USER_B}'::uuid, '${ORG_B}'::uuid, 'iso-b@ibex.local', 'ISO User B', 'owner', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
VALUES (
  '${AGENT_B}'::uuid, '${ORG_B}'::uuid, '${USER_B}'::uuid,
  'ISO Agent B', 'iso-agent-b', 'active'
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
  'ISO Org B Seed Token',
  270633733891,
  false
) ON CONFLICT (id) DO NOTHING;

-- User B inside Org A + agent created_by that user (ISO-MCP-02).
INSERT INTO ibex_core.users (id, org_id, email, name, role, status)
VALUES (
  '${USER_A2}'::uuid, '${ORG_A}'::uuid, 'iso-a2@ibex.local', 'ISO OrgA User B', 'member', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
VALUES (
  '${AGENT_USER_B}'::uuid, '${ORG_A}'::uuid, '${USER_A2}'::uuid,
  'ISO Agent By User B', 'iso-agent-by-user-b', 'active'
) ON CONFLICT (id) DO NOTHING;

-- Org-scoped PAT (agent_id NULL) for Org A.
INSERT INTO ibex_core.tokens (
  id, org_id, user_id, agent_id, type, hash, prefix, name, permissions, is_revoked
) VALUES (
  '${TOKEN_ORG_ID}'::uuid,
  '${ORG_A}'::uuid,
  '00000000-0000-0000-0000-000000000002'::uuid,
  NULL,
  'pat',
  '${TOKEN_ORG_HASH}',
  '${TOKEN_ORG_PREFIX}',
  'ISO Org A Org-Scoped Token',
  270633733891,
  false
) ON CONFLICT (id) DO NOTHING;

-- Suspended agent + agent-scoped PAT (ISO-MCP-03).
INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
VALUES (
  '${AGENT_SUSPENDED}'::uuid, '${ORG_A}'::uuid,
  '00000000-0000-0000-0000-000000000002'::uuid,
  'ISO Suspended Agent', 'iso-agent-suspended', 'suspended'
) ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;

INSERT INTO ibex_core.tokens (
  id, org_id, user_id, agent_id, type, hash, prefix, name, permissions, is_revoked
) VALUES (
  '${TOKEN_SUSPENDED_ID}'::uuid,
  '${ORG_A}'::uuid,
  '00000000-0000-0000-0000-000000000002'::uuid,
  '${AGENT_SUSPENDED}'::uuid,
  'pat',
  '${TOKEN_SUSPENDED_HASH}',
  '${TOKEN_SUSPENDED_PREFIX}',
  'ISO Suspended Agent Token',
  270633733891,
  false
) ON CONFLICT (id) DO NOTHING;
SQL
  pass "seeded Org A/B + ISO-MCP fixtures"
}

start_stack() {
  mkdir -p "$LOG_DIR"
  unset CLICKHOUSE_DSN || true
  unset OTEL_EXPORTER_OTLP_ENDPOINT || true

  local auth_bin
  auth_bin="$LOG_DIR/ibex-auth"
  echo "security-p35: building auth → ${auth_bin}..."
  go build -o "$auth_bin" ./services/auth/cmd/auth

  echo "security-p35: starting auth on :${AUTH_HTTP_PORT}/:${AUTH_GRPC_PORT}..."
  IBEX_PORT="$AUTH_HTTP_PORT" IBEX_GRPC_PORT="$AUTH_GRPC_PORT" OTEL_SERVICE_NAME=ibex-auth \
    "$auth_bin" >"$LOG_DIR/auth.log" 2>&1 &
  PIDS+=("$!")
  wait_http "auth" "http://127.0.0.1:${AUTH_HTTP_PORT}/health"

  echo "security-p35: starting stub TEI on :${STUB_TEI_PORT}..."
  (
    cd "$EMBEDDER_DIR"
    if [[ ! -d .venv ]]; then
      uv sync --frozen --no-build >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec env PYTHONPATH="$EMBEDDER_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python "$STUB_TEI_PY" --host 127.0.0.1 --port "$STUB_TEI_PORT"
  ) >"$LOG_DIR/stub-tei.log" 2>&1 &
  PIDS+=("$!")
  wait_http "stub-tei" "http://127.0.0.1:${STUB_TEI_PORT}/health"

  echo "security-p35: starting embedder on :${EMBEDDER_PORT}..."
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
      uvicorn app.main:app --host 127.0.0.1 --port "$EMBEDDER_PORT"
  ) >"$LOG_DIR/embedder.log" 2>&1 &
  PIDS+=("$!")
  wait_http "embedder" "http://127.0.0.1:${EMBEDDER_PORT}/health"

  echo "security-p35: starting memory on :${MEMORY_PORT}..."
  (
    cd "$MEMORY_DIR"
    if [[ ! -d .venv ]]; then
      bash "$ROOT/infra/scripts/memory-uv-sync.sh" >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec env \
      IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}" \
      IBEX_MEMORY_AUTH_TIMEOUT_MS="${IBEX_MEMORY_AUTH_TIMEOUT_MS:-2000}" \
      IBEX_MEMORY_EMBEDDING_BASE_URL="http://127.0.0.1:${EMBEDDER_PORT}" \
      IBEX_EMBEDDING_API_TOKEN="$EMBED_TOKEN" \
      IBEX_MEMORY_DATABASE_URL="${POSTGRES_DSN}" \
      IBEX_MEMORY_REDIS_URL="${REDIS_URL}" \
      uvicorn app.main:app --host 127.0.0.1 --port "$MEMORY_PORT"
  ) >"$LOG_DIR/memory.log" 2>&1 &
  PIDS+=("$!")
  wait_http "memory" "http://127.0.0.1:${MEMORY_PORT}/health" 180
  wait_http "memory" "http://127.0.0.1:${MEMORY_PORT}/ready" 180
}

run_iso_tests() {
  export IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}"
  export IBEX_MEMORY_HTTP_URL="http://127.0.0.1:${MEMORY_PORT}"
  export IBEX_ISO_MCP_TOKEN_A="$TOKEN_A"
  export IBEX_ISO_MCP_TOKEN_ORG_SCOPED="$TOKEN_ORG"
  export IBEX_ISO_MCP_TOKEN_SUSPENDED="$TOKEN_SUSPENDED"
  export IBEX_ISO_MCP_ORG_A="$ORG_A"
  export IBEX_ISO_MCP_ORG_B="$ORG_B"
  export IBEX_ISO_MCP_AGENT_B="$AGENT_B"
  export IBEX_ISO_MCP_AGENT_USER_B="$AGENT_USER_B"
  export IBEX_ISO_MCP_AGENT_SUSPENDED="$AGENT_SUSPENDED"

  bash "$ROOT/infra/scripts/mcp-memory-uv-sync.sh"
  bash "$ROOT/infra/scripts/worker-uv-sync.sh"

  local mcp_count worker_count total
  mcp_count="$(
    cd "$MCP_DIR"
    .venv/bin/pytest -q -m iso_mcp --collect-only 2>/dev/null \
      | grep -c 'ISO-MCP-0\|iso_mcp_0\|test_iso_mcp_' || true
  )"
  worker_count="$(
    cd "$WORKER_DIR"
    .venv/bin/pytest -q -m iso_mcp --collect-only 2>/dev/null \
      | grep -c 'ISO-MCP-0\|iso_mcp_0\|test_iso_mcp_' || true
  )"
  total=$((mcp_count + worker_count))
  if [[ "$total" -lt 4 ]]; then
    echo "expected at least 4 iso_mcp tests, found ${total} (mcp=${mcp_count} worker=${worker_count})" >&2
    exit 1
  fi
  pass "iso_mcp collect count=${total} (mcp=${mcp_count} worker=${worker_count})"

  (
    cd "$MCP_DIR"
    .venv/bin/pytest -q -m iso_mcp
  )
  (
    cd "$WORKER_DIR"
    .venv/bin/pytest -q -m iso_mcp
  )
}

bash "$ROOT/infra/scripts/db-migrate.sh" up
seed_stack
start_stack
run_iso_tests
pass "security-integration-p3.5 complete"
