#!/usr/bin/env bash
# Start auth+proxy+embedder+mcp on demo ports, generate Phase 1–2.5 traffic,
# and assert Prometheus/Grafana see live ibex_* series.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="${IBEX_OBS_LIVE_LOG_DIR:-/tmp/ibex-obs-live}"
mkdir -p "$LOG_DIR"
PIDS=()

# RUN_START bounds the Tempo trace search to *this* run. Searching "the last
# hour" made the assertion pass on a stale trace: a leftover from an earlier run
# sits inside the window, so a current export failure is masked and the check
# reports a trace it did not produce. Everything this script starts begins after
# this instant, so a trace with an earlier start cannot be evidence for it.
RUN_START="$(date +%s)"

PROXY_ADDR="${IBEX_PROXY_ADDR:-http://127.0.0.1:18080}"
AUTH_HTTP="${IBEX_AUTH_HTTP:-http://127.0.0.1:18081}"
AUTH_GRPC_PORT="${IBEX_GRPC_PORT:-19091}"
EMBEDDER_ADDR="${IBEX_EMBEDDER_ADDR:-http://127.0.0.1:18004}"
MCP_ADDR="${IBEX_MCP_ADDR:-http://127.0.0.1:18090}"
PROM_URL="${IBEX_OBS_PROMETHEUS_URL:-http://127.0.0.1:19090}"
GRAFANA_URL="${IBEX_OBS_GRAFANA_URL:-http://127.0.0.1:3000}"
TEMPO_URL="${IBEX_OBS_TEMPO_URL:-http://127.0.0.1:3200}"
DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
DEV_AGENT="${IBEX_DEV_AGENT_ID:-00000000-0000-0000-0000-000000000003}"
EMBED_TOKEN="${IBEX_EMBEDDING_API_TOKEN:-dev-embedder-metrics-token}"
CHAT_BODY='{"model":"gpt-4o","messages":[{"role":"user","content":"obs live verify"}]}'
KEEP="${IBEX_OBS_LIVE_KEEP:-1}"
PORT_FROM_URL_SED='s#.*:([0-9]+).*#\1#'
JSON_CONTENT_TYPE='Content-Type: application/json'

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

cleanup() {
  if [[ "$KEEP" == "1" ]]; then
    echo "IBEX_OBS_LIVE_KEEP=1: leaving services up (pids ${PIDS[*]:-none})"
    printf '%s\n' "${PIDS[@]:-}" >"$LOG_DIR/pids.txt"
    return 0
  fi
  local pid
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

wait_http() {
  local name="$1" url="$2"
  for _ in $(seq 1 90); do
    if curl -fsS --connect-timeout 1 --max-time 2 "$url" >/dev/null 2>&1; then
      pass "$name ready"
      return 0
    fi
    sleep 0.5
  done
  fail "$name not ready: $url"
}

prom_query() {
  local query="$1"
  curl -fsS --connect-timeout 2 --max-time 10 \
    --get --data-urlencode "query=${query}" "$PROM_URL/api/v1/query"
}

# tempo_ready separates "Tempo is not running" from "Tempo is running but empty".
tempo_ready() {
  curl -fsS --connect-timeout 2 --max-time 5 "$TEMPO_URL/ready" >/dev/null 2>&1
}

# TRACE_SERVICE is the resource service.name the proxy actually exports, not a
# guess: services/proxy/internal/bootstrap/run.go pins bootstrapServiceName =
# "ibex-proxy" and passes it to telemetry.InitTracer, and
# packages/telemetry/resource.go turns that into semconv.ServiceName. Tempo's
# search returns every service in the window, so without this filter a trace from
# auth, the embedder or an earlier run satisfies the assertion.
TRACE_SERVICE="ibex-proxy"

# tempo_search asks for the newest single ibex-proxy trace that started after
# this script did. Both bounds are sent explicitly:
#   * `q={service.name="ibex-proxy"}` keeps another service's traffic from
#     standing in for the proxy's export path;
#   * `start=${RUN_START}` keeps an earlier run's trace from masking a current
#     export failure — the failure mode that made this assertion unfalsifiable.
# Relying on Tempo's default window would silently test a different range than
# the operator expects.
tempo_search() {
  local end
  end=$(date +%s)
  # Keep the window non-degenerate: the first iteration can run inside the same
  # second as RUN_START, and start == end is an empty range.
  [[ "$end" -le "$RUN_START" ]] && end=$((RUN_START + 1))
  curl -fsS --connect-timeout 2 --max-time 10 --get \
    --data-urlencode "limit=1" \
    --data-urlencode 'q={service.name="'"$TRACE_SERVICE"'"}' \
    --data-urlencode "start=${RUN_START}" \
    --data-urlencode "end=${end}" \
    "$TEMPO_URL/api/search"
}

# tempo_first_trace_id prints the trace id of the first search hit and exits 1
# when the payload has none (or cannot be parsed), so the caller can tell an
# empty Tempo from a successful round-trip.
tempo_first_trace_id() {
  python3 -c '
import json, sys

try:
    payload = json.load(sys.stdin)
except (OSError, ValueError):
    sys.exit(1)
traces = payload.get("traces") or []
if not traces:
    sys.exit(1)
trace_id = traces[0].get("traceID") or ""
if not trace_id:
    sys.exit(1)
print(trace_id)
'
}

assert_series() {
  local label="$1" query="$2"
  local body
  body="$(prom_query "$query")"
  echo "$body" | grep -q '"resultType":"vector"' || fail "bad prometheus response for $label"
  if echo "$body" | grep -q '"result":\[\]'; then
    fail "no series for $label ($query)"
  fi
  pass "prometheus series: $label"
}

echo "=== Observability live verify (auth/proxy/embedder/mcp → Grafana) ==="

# Reload prometheus config (demo scrape jobs).
if curl -fsS -X POST "$PROM_URL/-/reload" >/dev/null 2>&1; then
  pass "prometheus config reload"
else
  echo "WARN: prometheus reload failed; restart observability stack if targets stay down"
fi

bash "$ROOT_DIR/infra/scripts/db-seed.sh" >/dev/null

export IBEX_ENV=development
export POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export IBEX_LLM_MODE=mock
export IBEX_AUTH_VALIDATE_TIMEOUT=2s
export OTEL_EXPORTER_OTLP_ENDPOINT=127.0.0.1:4317
export OTEL_SAMPLE_RATIO=1.0
unset CLICKHOUSE_DSN || true

proxy_port="$(echo "$PROXY_ADDR" | sed -E "$PORT_FROM_URL_SED")"
auth_http_port="$(echo "$AUTH_HTTP" | sed -E "$PORT_FROM_URL_SED")"
embedder_port="$(echo "$EMBEDDER_ADDR" | sed -E "$PORT_FROM_URL_SED")"
mcp_port="$(echo "$MCP_ADDR" | sed -E "$PORT_FROM_URL_SED")"

# Stop leftovers on demo ports
for p in "$proxy_port" "$auth_http_port" "$embedder_port" "$mcp_port" "$AUTH_GRPC_PORT"; do
  fuser -k "${p}/tcp" 2>/dev/null || true
done
sleep 1

echo "starting auth..."
IBEX_PORT="$auth_http_port" IBEX_GRPC_PORT="$AUTH_GRPC_PORT" OTEL_SERVICE_NAME=ibex-auth \
  go run ./services/auth/cmd/auth >"$LOG_DIR/auth.log" 2>&1 &
PIDS+=("$!")
wait_http "auth" "$AUTH_HTTP/health"

echo "starting proxy..."
IBEX_PORT="$proxy_port" IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}" OTEL_SERVICE_NAME=ibex-proxy \
  go run ./services/proxy/cmd/proxy >"$LOG_DIR/proxy.log" 2>&1 &
PIDS+=("$!")

echo "starting embedder..."
(
  cd "$ROOT_DIR/services/embedder"
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

echo "starting mcp-memory..."
(
  cd "$ROOT_DIR/services/mcp-memory"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  export IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}"
  export IBEX_MCP_AUTH_TIMEOUT_MS=2000
  export IBEX_MCP_HOST=127.0.0.1
  export IBEX_MCP_PORT="$mcp_port"
  export IBEX_MCP_RESOURCE_URL="http://127.0.0.1:${mcp_port}/mcp"
  export IBEX_MCP_AUTH_SERVER_URL="http://127.0.0.1:${proxy_port}"
  # Compose-dev ClickHouse uses CLICKHOUSE_PASSWORD=ibexdev (see infra/compose/dev/.env.example).
  export IBEX_MCP_CLICKHOUSE_URL="${IBEX_MCP_CLICKHOUSE_URL:-http://default:ibexdev@127.0.0.1:8123}"
  exec uvicorn app.main:app --host 127.0.0.1 --port "$mcp_port"
) >"$LOG_DIR/mcp.log" 2>&1 &
PIDS+=("$!")
wait_http "mcp" "$MCP_ADDR/health"

echo "=== generating Phase 1–2 style traffic ==="
# Auth probes + chat (proxy critical path)
for i in $(seq 1 25); do
  curl -fsS -o /dev/null -X POST "$PROXY_ADDR/v1/chat/completions" \
    -H "$JSON_CONTENT_TYPE" \
    -H "Authorization: Bearer $DEV_TOKEN" \
    -H "X-IBEX-Agent-ID: $DEV_AGENT" \
    -d "$CHAT_BODY" || true
  curl -fsS -o /dev/null -H "Authorization: Bearer $DEV_TOKEN" \
    -H "X-IBEX-Agent-ID: $DEV_AGENT" \
    "$PROXY_ADDR/v1/internal/auth-probe" || true
done
# Intentional failures for error-rate panels
curl -fsS -o /dev/null -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "$JSON_CONTENT_TYPE" -d "$CHAT_BODY" || true
curl -fsS -o /dev/null -H "Authorization: Bearer bad" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "$JSON_CONTENT_TYPE" -d "$CHAT_BODY" || true

# Auth HTTP + metrics scrape
for i in $(seq 1 10); do
  curl -fsS -o /dev/null "$AUTH_HTTP/health"
  curl -fsS -o /dev/null "$AUTH_HTTP/metrics"
done

# Embedder
for i in $(seq 1 15); do
  curl -fsS -o /dev/null -X POST "$EMBEDDER_ADDR/v1/embed" \
    -H "Authorization: Bearer $EMBED_TOKEN" \
    -H "$JSON_CONTENT_TYPE" \
    -d '{"texts":["obs live '"$i"'"],"org_id":"00000000-0000-0000-0000-000000000001"}' || true
done
curl -fsS -o /dev/null -H "Authorization: Bearer $EMBED_TOKEN" "$EMBEDDER_ADDR/metrics"

# MCP tools (live auth)
MCP_HEADERS=(-H "Authorization: Bearer $DEV_TOKEN" -H "Accept: application/json, text/event-stream" -H "$JSON_CONTENT_TYPE")
curl -fsS -o /dev/null -X POST "$MCP_ADDR/mcp" "${MCP_HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"obs-live","version":"0"}}}' || true
curl -fsS -o /dev/null -X POST "$MCP_ADDR/mcp" "${MCP_HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' || true
for i in $(seq 1 10); do
  curl -fsS -o /dev/null -X POST "$MCP_ADDR/mcp" "${MCP_HEADERS[@]}" \
    -d '{"jsonrpc":"2.0","id":'"$i"',"method":"tools/call","params":{"name":"search_memory","arguments":{"query":"obs'"$i"'"}}}' || true
done
curl -fsS -o /dev/null "$MCP_ADDR/metrics"
pass "traffic generated"

echo "waiting for Prometheus scrape (25s)..."
sleep 25

echo "=== Prometheus targets ==="
targets="$(curl -fsS "$PROM_URL/api/v1/targets")"
for job in proxy-demo auth-demo embedder-demo mcp-memory-demo; do
  echo "$targets" | grep -q "\"job\":\"$job\"" || fail "missing job $job"
  # health up for demo jobs
  if ! echo "$targets" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ups=[t for t in d['data']['activeTargets'] if t['labels'].get('job')=='$job' and t.get('health')=='up']
sys.exit(0 if ups else 1)
"; then
    fail "job $job not UP"
  fi
  pass "target UP: $job"
done

echo "=== Prometheus ibex_* series ==="
assert_series "proxy requests" 'sum(rate(ibex_proxy_requests_total[2m]))'
assert_series "proxy auth duration" 'histogram_quantile(0.95, sum(rate(ibex_proxy_auth_duration_seconds_bucket[2m])) by (le))'
assert_series "auth http requests" 'sum(rate(ibex_auth_http_requests_total[2m])) or sum(rate(ibex_auth_grpc_requests_total[2m]))'
assert_series "auth validate" 'histogram_quantile(0.95, sum(rate(ibex_auth_validate_token_duration_seconds_bucket[2m])) by (le))'
assert_series "embedder http" 'sum(rate(ibex_embedder_http_requests_total[2m]))'
assert_series "mcp http" 'sum(rate(ibex_mcp_http_requests_total[2m]))'
assert_series "mcp audit" 'sum(rate(ibex_mcp_audit_emitted_total[2m])) or sum(ibex_mcp_audit_emitted_total) or sum(rate(ibex_mcp_audit_sink_errors_total[2m]))'
assert_series "process_up" 'ibex_process_up'

echo "=== Grafana dashboards queryable ==="
for uid in ibex-system-overview ibex-proxy-critical-path ibex-auth ibex-embedder-mcp; do
  code="$(curl -fsS -o /dev/null -w '%{http_code}' "$GRAFANA_URL/api/dashboards/uid/$uid")"
  [[ "$code" == "200" ]] || fail "grafana dashboard $uid -> $code"
  pass "grafana dashboard: $uid"
done

# Prefer Prometheus HTTP API already validated; also hit Grafana datasource health
ds="$(curl -fsS "$GRAFANA_URL/api/datasources/uid/prometheus")"
echo "$ds" | grep -q '"uid":"prometheus"' || fail "grafana prometheus datasource missing"
pass "grafana prometheus datasource"

echo "=== Tempo trace round-trip ==="
# Tempo is part of this stack (infra/compose/observability/docker-compose.yml) and
# the services started above export OTLP to the collector through
# OTEL_EXPORTER_OTLP_ENDPOINT, so a trace asserted here is the end-to-end path
# W6.4 asks for: service -> collector -> Tempo -> query.
#
# The two failure modes are reported differently on purpose. An unreachable Tempo
# is an infrastructure problem (nothing is running); a reachable Tempo with no
# trace is an export problem (the collector, the exporter, or sampling), and
# conflating them turns a five-minute fix into an hour of guessing. This
# replaced an assertion that queried Prometheus `up` while claiming to check
# Tempo, which could never fail for a Tempo problem.
#
# The search is narrowed twice (see tempo_search): to service.name="ibex-proxy"
# and to traces that started after RUN_START. An unfiltered "newest trace in the
# last hour" passed on leftovers from an earlier run, so a broken export path
# stayed green for as long as one old trace remained in the window.
if ! tempo_ready; then
  fail "Tempo unreachable at ${TEMPO_URL}/ready: start it with 'make observability-up' (services export OTLP to ${OTEL_EXPORTER_OTLP_ENDPOINT})"
fi
pass "tempo ready"

trace_id=""
for _ in $(seq 1 30); do
  if trace_id="$(tempo_search 2>/dev/null | tempo_first_trace_id 2>/dev/null)"; then
    [[ -n "$trace_id" ]] && break
  fi
  trace_id=""
  sleep 2
done
if [[ -z "$trace_id" ]]; then
  fail "Tempo is reachable at ${TEMPO_URL} but returned no ${TRACE_SERVICE} trace that started after this run began (${RUN_START}): either OTLP export from the proxy is not reaching it (check the otel-collector log; endpoint ${OTEL_EXPORTER_OTLP_ENDPOINT}, service.name=${TRACE_SERVICE}) or its search API returned an unparseable response. A stale trace from an earlier run is not accepted as evidence."
fi
pass "tempo trace found: ${trace_id}"

echo ""
echo "observability-live-verify passed"
echo "Open Grafana: $GRAFANA_URL  (IBEX folder dashboards)"
echo "  Proxy Critical Path: $GRAFANA_URL/d/ibex-proxy-critical-path"
echo "  Auth:               $GRAFANA_URL/d/ibex-auth"
echo "  Embedder+MCP:       $GRAFANA_URL/d/ibex-embedder-mcp"
echo "  System Overview:    $GRAFANA_URL/d/ibex-system-overview"
echo "Prometheus: $PROM_URL"
echo "Tempo:      $TEMPO_URL  (trace ${trace_id} is searchable)"
echo "Services kept running (KEEP=$KEEP). Logs: $LOG_DIR"
