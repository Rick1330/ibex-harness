#!/usr/bin/env bash
# Hit local service probe/metrics endpoints so Grafana/Prometheus have series.
# Does not require auth+proxy chat traffic (use make dev-smoke for that).
set -euo pipefail

PROXY_ADDR="${IBEX_PROXY_ADDR:-http://127.0.0.1:8080}"
AUTH_ADDR="${IBEX_AUTH_HTTP_ADDR:-http://127.0.0.1:8081}"
EMBEDDER_ADDR="${IBEX_EMBEDDER_ADDR:-http://127.0.0.1:8004}"
MCP_ADDR="${IBEX_MCP_ADDR:-http://127.0.0.1:8090}"
EMBED_TOKEN="${IBEX_EMBEDDING_API_TOKEN:-dev-embedder-metrics-token}"

hit() {
  local name="$1"
  shift
  if curl -fsS --connect-timeout 2 --max-time 5 "$@" >/dev/null 2>&1; then
    echo "ok: $name"
  else
    echo "skip: $name (not reachable)"
  fi
}

hit "proxy /health" "$PROXY_ADDR/health"
hit "proxy /metrics" "$PROXY_ADDR/metrics"
hit "auth /health" "$AUTH_ADDR/health"
hit "auth /metrics" "$AUTH_ADDR/metrics"
hit "embedder /health" "$EMBEDDER_ADDR/health"
hit "embedder /metrics" -H "Authorization: Bearer $EMBED_TOKEN" "$EMBEDDER_ADDR/metrics"
hit "mcp /health" "$MCP_ADDR/health"
hit "mcp /metrics" "$MCP_ADDR/metrics"

echo "observability-traffic: done (wait ~15s for Prometheus scrape)"
