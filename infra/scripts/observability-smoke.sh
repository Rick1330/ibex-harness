#!/usr/bin/env bash
# Smoke-check local LGTM stack: Grafana, Prometheus ready, optional ibex_* series.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
if [[ -f "$ROOT_DIR/infra/compose/observability/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/infra/compose/observability/.env"
  set +a
fi

PROM_URL="${IBEX_OBS_PROMETHEUS_URL:-http://127.0.0.1:${IBEX_OBS_PROMETHEUS_PORT:-9090}}"
GRAFANA_URL="${IBEX_OBS_GRAFANA_URL:-http://127.0.0.1:${IBEX_OBS_GRAFANA_PORT:-3000}}"
TEMPO_URL="${IBEX_OBS_TEMPO_URL:-http://127.0.0.1:${IBEX_OBS_TEMPO_PORT:-3200}}"
LOKI_URL="${IBEX_OBS_LOKI_URL:-http://127.0.0.1:${IBEX_OBS_LOKI_PORT:-3100}}"
REQUIRE_IBEX_SERIES="${IBEX_OBS_REQUIRE_IBEX_SERIES:-0}"
CURL_MAX_TIME="${CURL_MAX_TIME:-10}"

check_200() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -fsS --connect-timeout 5 --max-time "$CURL_MAX_TIME" -o /dev/null -w '%{http_code}' "$url" || true)"
  if [[ "$code" != "200" && "$code" != "204" ]]; then
    echo "observability-smoke failed: $name $url -> HTTP $code"
    exit 1
  fi
  echo "ok: $name"
}

check_200 "grafana health" "${GRAFANA_URL}/api/health"
check_200 "prometheus ready" "${PROM_URL}/-/ready"
check_200 "tempo ready" "${TEMPO_URL}/ready"
OTEL_HEALTH_URL="${IBEX_OBS_OTEL_HEALTH_URL:-http://127.0.0.1:${IBEX_OBS_OTEL_HEALTH_PORT:-13133}/}"
check_200 "otel collector health" "$OTEL_HEALTH_URL"
# Loki ready path depends on config; try both.
loki_code="$(curl -fsS --connect-timeout 5 --max-time "$CURL_MAX_TIME" -o /dev/null -w '%{http_code}' "${LOKI_URL}/ready" || true)"
if [[ "$loki_code" != "200" ]]; then
  loki_code="$(curl -fsS --connect-timeout 5 --max-time "$CURL_MAX_TIME" -o /dev/null -w '%{http_code}' "${LOKI_URL}/loki/ready" || true)"
fi
if [[ "$loki_code" != "200" ]]; then
  echo "observability-smoke failed: loki ready -> HTTP $loki_code"
  exit 1
fi
echo "ok: loki ready"

dashboards_json="$(curl -fsS --connect-timeout 5 --max-time "$CURL_MAX_TIME" "${GRAFANA_URL}/api/search?query=IBEX" || true)"
for uid in ibex-system-overview ibex-proxy-critical-path ibex-auth ibex-embedder-mcp; do
  if ! grep -q "$uid" <<<"$dashboards_json"; then
    echo "observability-smoke failed: Grafana dashboard uid $uid not found"
    exit 1
  fi
done
echo "ok: grafana dashboards provisioned"

targets_json="$(curl -fsS --connect-timeout 5 --max-time "$CURL_MAX_TIME" "${PROM_URL}/api/v1/targets" || true)"
if ! grep -q '"job":"prometheus"' <<<"$targets_json"; then
  echo "observability-smoke failed: prometheus self-scrape target missing"
  exit 1
fi
echo "ok: prometheus targets API"

if [[ "$REQUIRE_IBEX_SERIES" == "1" ]]; then
  series="$(curl -fsS --connect-timeout 5 --max-time "$CURL_MAX_TIME" \
    --get --data-urlencode 'match[]={__name__=~"ibex_.*"}' \
    "${PROM_URL}/api/v1/series" || true)"
  if ! grep -q '"status":"success"' <<<"$series" || ! grep -q 'ibex_' <<<"$series"; then
    echo "observability-smoke failed: no ibex_* series (start services + traffic, or unset IBEX_OBS_REQUIRE_IBEX_SERIES)"
    exit 1
  fi
  echo "ok: ibex_* series present"
else
  echo "skip: ibex_* series check (set IBEX_OBS_REQUIRE_IBEX_SERIES=1 after generating traffic)"
fi

echo "observability-smoke passed"
