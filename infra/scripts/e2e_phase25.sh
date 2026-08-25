#!/usr/bin/env bash
# Multi-service Phase 2.5 e2e: auth + proxy + embedder + mcp-memory.
#
# Modes:
#   IBEX_E2E_PHASE25_MANAGE=1 (default) — start/stop processes for this script
#   IBEX_E2E_PHASE25_MANAGE=0 — use already-running services on default ports
#
# Prerequisites (manage mode): make compose-dev-up && make db-migrate && make db-seed
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PROXY_ADDR="${IBEX_PROXY_ADDR:-http://127.0.0.1:18080}"
AUTH_HTTP="${IBEX_AUTH_HTTP:-http://127.0.0.1:18081}"
AUTH_GRPC_PORT="${IBEX_GRPC_PORT:-19091}"
EMBEDDER_ADDR="${IBEX_EMBEDDER_ADDR:-http://127.0.0.1:18004}"
MCP_ADDR="${IBEX_MCP_ADDR:-http://127.0.0.1:18090}"
DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
DEV_AGENT="${IBEX_DEV_AGENT_ID:-00000000-0000-0000-0000-000000000003}"
EMBED_TOKEN="${IBEX_EMBEDDING_API_TOKEN:-dev-embedder-metrics-token}"
MANAGE="${IBEX_E2E_PHASE25_MANAGE:-1}"
LOG_DIR="${IBEX_E2E_PHASE25_LOG_DIR:-/tmp/ibex-e2e-phase25}"
CHAT_BODY='{"model":"gpt-4o","messages":[{"role":"user","content":"phase25 e2e"}]}'
# OTel gRPC WithEndpoint expects host:port (no scheme). Empty disables export.
OTEL_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-}"

PIDS=()
BODY_FILE=""
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

expect_http() {
  local got="$1"
  local want="$2"
  local ok_msg="$3"
  local fail_msg="$4"
  if [[ "$got" == "$want" ]]; then
    pass "$ok_msg"
  else
    fail "$fail_msg"
  fi
}

expect_http_any() {
  local got="$1"
  local ok_msg="$2"
  local fail_msg="$3"
  shift 3
  local want
  for want in "$@"; do
    if [[ "$got" == "$want" ]]; then
      pass "$ok_msg"
      return 0
    fi
  done
  fail "$fail_msg"
}

cleanup() {
  if [[ -n "${BODY_FILE:-}" && -f "$BODY_FILE" ]]; then
    rm -f "$BODY_FILE"
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
  for _ in $(seq 1 90); do
    if curl -fsS --connect-timeout 1 --max-time 2 "$url" >/dev/null 2>&1; then
      pass "$name ready ($url)"
      return 0
    fi
    sleep 0.5
  done
  fail "$name not ready: $url"
}

http_code() {
  if [[ -z "${BODY_FILE:-}" ]]; then
    BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/ibex-e2e-body.XXXXXX")"
  fi
  curl -sS -o "$BODY_FILE" -w "%{http_code}" "$@" || true
}

start_stack() {
  mkdir -p "$LOG_DIR"
  export IBEX_ENV=development
  export POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
  export IBEX_LLM_MODE="${IBEX_LLM_MODE:-mock}"
  export IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}"
  # Avoid accidental CLICKHOUSE_DSN=host:port (OTEL-style) polluting proxy startup logs.
  if [[ -z "${CLICKHOUSE_DSN:-}" ]]; then
    unset CLICKHOUSE_DSN || true
  fi
  if [[ -n "$OTEL_ENDPOINT" ]]; then
    # Strip scheme if an operator pasted http://host:port
    export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_ENDPOINT#http://}"
    export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT#https://}"
    export OTEL_SAMPLE_RATIO="${OTEL_SAMPLE_RATIO:-1.0}"
  else
    unset OTEL_EXPORTER_OTLP_ENDPOINT || true
  fi

  local proxy_port auth_http_port embedder_port mcp_port
  proxy_port="$(echo "$PROXY_ADDR" | sed -E 's#.*:([0-9]+).*#\1#')"
  auth_http_port="$(echo "$AUTH_HTTP" | sed -E 's#.*:([0-9]+).*#\1#')"
  embedder_port="$(echo "$EMBEDDER_ADDR" | sed -E 's#.*:([0-9]+).*#\1#')"
  mcp_port="$(echo "$MCP_ADDR" | sed -E 's#.*:([0-9]+).*#\1#')"

  echo "e2e-phase25: starting auth on :${auth_http_port}/:${AUTH_GRPC_PORT}..."
  IBEX_PORT="$auth_http_port" IBEX_GRPC_PORT="$AUTH_GRPC_PORT" OTEL_SERVICE_NAME=ibex-auth \
    go run ./services/auth/cmd/auth >"$LOG_DIR/auth.log" 2>&1 &
  PIDS+=("$!")

  wait_http "auth" "$AUTH_HTTP/health"

  echo "e2e-phase25: starting proxy on :${proxy_port}..."
  IBEX_PORT="$proxy_port" IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}" OTEL_SERVICE_NAME=ibex-proxy \
    go run ./services/proxy/cmd/proxy >"$LOG_DIR/proxy.log" 2>&1 &
  PIDS+=("$!")

  echo "e2e-phase25: starting embedder (cpu stub) on :${embedder_port}..."
  (
    cd "$ROOT_DIR/services/embedder"
    if [[ ! -d .venv ]]; then
      # Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
      uv sync --frozen --no-build >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    export IBEX_EMBEDDING_PROFILE=cpu
    export IBEX_EMBEDDING_API_TOKEN="$EMBED_TOKEN"
    export IBEX_EMBEDDING_CACHE_ENABLED=false
    exec uvicorn app.main:app --host 127.0.0.1 --port "$embedder_port"
  ) >"$LOG_DIR/embedder.log" 2>&1 &
  PIDS+=("$!")

  wait_http "proxy" "$PROXY_ADDR/health"
  wait_http "embedder" "$EMBEDDER_ADDR/health"

  echo "e2e-phase25: starting mcp-memory on :${mcp_port} (after auth ready)..."
  (
    cd "$ROOT_DIR/services/mcp-memory"
    if [[ ! -d .venv ]]; then
      # Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
      uv sync --frozen --no-build --extra dev >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    export IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}"
    export IBEX_MCP_AUTH_TIMEOUT_MS="${IBEX_MCP_AUTH_TIMEOUT_MS:-2000}"
    export IBEX_MCP_HOST=127.0.0.1
    export IBEX_MCP_PORT="$mcp_port"
    export IBEX_MCP_RESOURCE_URL="http://127.0.0.1:${mcp_port}/mcp"
    export IBEX_MCP_AUTH_SERVER_URL="http://127.0.0.1:${proxy_port}"
    export IBEX_MCP_CLICKHOUSE_URL="${IBEX_MCP_CLICKHOUSE_URL:-http://default:ibexdev@127.0.0.1:8123}"
    exec uvicorn app.main:app --host 127.0.0.1 --port "$mcp_port"
  ) >"$LOG_DIR/mcp.log" 2>&1 &
  PIDS+=("$!")

  wait_http "mcp" "$MCP_ADDR/health"
}

echo "=== Phase 2.5 multi-service e2e ==="
echo "  manage=$MANAGE logs=$LOG_DIR"

if [[ "$MANAGE" == "1" ]]; then
  if ! curl -fsS --connect-timeout 2 "http://127.0.0.1:5432" >/dev/null 2>&1 \
    && ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ibex-dev-postgres; then
    fail "compose-dev Postgres not available (make compose-dev-up && make db-migrate && make db-seed)"
  fi
  bash "$ROOT_DIR/infra/scripts/db-seed.sh" >/dev/null
  start_stack
else
  wait_http "auth" "$AUTH_HTTP/health"
  wait_http "proxy" "$PROXY_ADDR/health"
  wait_http "embedder" "$EMBEDDER_ADDR/health"
  wait_http "mcp" "$MCP_ADDR/health"
fi

CODE="$(http_code "$PROXY_ADDR/ready")"
expect_http "$CODE" "200" "proxy /ready" "proxy /ready -> $CODE"

CODE="$(http_code "$AUTH_HTTP/ready")"
expect_http "$CODE" "200" "auth /ready" "auth /ready -> $CODE"

CODE="$(http_code "$EMBEDDER_ADDR/ready")"
expect_http "$CODE" "200" "embedder /ready" "embedder /ready -> $CODE (check cpu stub startup)"

CODE="$(http_code "$MCP_ADDR/ready")"
if [[ "$CODE" == "200" ]]; then
  pass "mcp /ready"
else
  echo "---- mcp log ----" >&2
  tail -n 40 "$LOG_DIR/mcp.log" 2>/dev/null >&2 || true
  fail "mcp /ready -> $CODE (auth gRPC must be reachable)"
fi

CODE="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  -d "$CHAT_BODY")"
if [[ "$CODE" == "200" ]]; then
  pass "proxy chat → 200"
else
  echo "---- proxy log ----" >&2
  tail -n 40 "$LOG_DIR/proxy.log" 2>/dev/null >&2 || true
  fail "proxy chat -> $CODE"
fi

CODE="$(http_code -X POST "$EMBEDDER_ADDR/v1/embed" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EMBED_TOKEN" \
  -d '{"texts":["phase25 e2e"],"org_id":"00000000-0000-0000-0000-000000000001"}')"
expect_http "$CODE" "200" "embedder /v1/embed → 200" \
  "embedder embed -> $CODE body=$(head -c 200 "${BODY_FILE:-/dev/null}" 2>/dev/null || true)"

MCP_HEADERS=(
  -H "Authorization: Bearer $DEV_TOKEN"
  -H "Accept: application/json, text/event-stream"
  -H "Content-Type: application/json"
)

CODE="$(http_code -X POST "$MCP_ADDR/mcp" "${MCP_HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"e2e-phase25","version":"0"}}}')"
expect_http_any "$CODE" "mcp initialize → $CODE" "mcp initialize -> $CODE" "200" "202"

curl -sS -X POST "$MCP_ADDR/mcp" "${MCP_HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null || true

CODE="$(http_code -X POST "$MCP_ADDR/mcp" "${MCP_HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')"
BODY="$(cat "${BODY_FILE:-/dev/null}" 2>/dev/null || true)"
if [[ "$CODE" != "200" && "$CODE" != "202" ]]; then
  fail "mcp tools/list -> $CODE"
fi
echo "$BODY" | grep -q search_memory || fail "mcp tools/list missing search_memory"
echo "$BODY" | grep -q write_memory || fail "mcp tools/list missing write_memory"
pass "mcp tools/list (live Auth ValidateToken)"

CODE="$(http_code -X POST "$MCP_ADDR/mcp" "${MCP_HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_memory","arguments":{"query":"phase25"}}}')"
expect_http_any "$CODE" "mcp tools/call search_memory → $CODE" "mcp tools/call -> $CODE" "200" "202"

CODE="$(http_code "$PROXY_ADDR/metrics")"
expect_http "$CODE" "200" "proxy /metrics" "proxy /metrics -> $CODE"
CODE="$(http_code -H "Authorization: Bearer $EMBED_TOKEN" "$EMBEDDER_ADDR/metrics")"
expect_http "$CODE" "200" "embedder /metrics" "embedder /metrics -> $CODE"
CODE="$(http_code "$MCP_ADDR/metrics")"
expect_http "$CODE" "200" "mcp /metrics" "mcp /metrics -> $CODE"

echo ""
echo "e2e-phase25 passed"
