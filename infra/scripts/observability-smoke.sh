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

if [[ "${IBEX_NETWORK:-bridge}" == host ]]; then
  PROM_URL="${IBEX_OBS_PROMETHEUS_URL:-http://127.0.0.1:9090}"
  GRAFANA_URL="${IBEX_OBS_GRAFANA_URL:-http://127.0.0.1:3000}"
  TEMPO_URL="${IBEX_OBS_TEMPO_URL:-http://127.0.0.1:3200}"
  LOKI_URL="${IBEX_OBS_LOKI_URL:-http://127.0.0.1:3100}"
  OTEL_HEALTH_URL="${IBEX_OBS_OTEL_HEALTH_URL:-http://127.0.0.1:13133/}"
  ALERTMANAGER_URL="${IBEX_OBS_ALERTMANAGER_URL:-http://127.0.0.1:9093}"
else
  PROM_URL="${IBEX_OBS_PROMETHEUS_URL:-http://127.0.0.1:${IBEX_OBS_PROMETHEUS_PORT:-9090}}"
  GRAFANA_URL="${IBEX_OBS_GRAFANA_URL:-http://127.0.0.1:${IBEX_OBS_GRAFANA_PORT:-3000}}"
  TEMPO_URL="${IBEX_OBS_TEMPO_URL:-http://127.0.0.1:${IBEX_OBS_TEMPO_PORT:-3200}}"
  LOKI_URL="${IBEX_OBS_LOKI_URL:-http://127.0.0.1:${IBEX_OBS_LOKI_PORT:-3100}}"
  OTEL_HEALTH_URL="${IBEX_OBS_OTEL_HEALTH_URL:-http://127.0.0.1:${IBEX_OBS_OTEL_HEALTH_PORT:-13133}/}"
  ALERTMANAGER_URL="${IBEX_OBS_ALERTMANAGER_URL:-http://127.0.0.1:${IBEX_OBS_ALERTMANAGER_PORT:-9093}}"
fi
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

# Alertmanager readiness is not enough: a null receiver accepts every alert and
# drops it, so a readiness-only smoke check passes while every page goes
# nowhere (P0-19 / W6.2). Assert the configuration the running Alertmanager
# serves. This is a shape check, not a delivery check: the base stack has no
# alert-receiver service, so nothing here proves the webhook URL resolves.
check_200 "alertmanager ready" "${ALERTMANAGER_URL}/-/ready"
am_status="$(curl -fsS --connect-timeout 5 --max-time "$CURL_MAX_TIME" "${ALERTMANAGER_URL}/api/v2/status" || true)"
if ! grep -q 'webhook_configs' <<<"$am_status"; then
  echo "observability-smoke failed: alertmanager config has no webhook_configs (alerts would be dropped)"
  exit 1
fi
if grep -q 'local-null' <<<"$am_status"; then
  echo "observability-smoke failed: alertmanager still routes to the null receiver (local-null)"
  exit 1
fi
# A webhook shape check passes for any receiver. Assert the two receivers this
# routing tree actually names, so a renamed or dropped receiver is caught here
# instead of surfacing as an alert that was never sent. Alertmanager serialises
# the served config into a JSON string, so match the receiver definition
# (`name: <receiver>`) without anchoring to a line.
for receiver in ibex-page ibex-digest; do
  if ! grep -qE "name: ['\"]?${receiver}['\"]?([^a-zA-Z0-9_-]|$)" <<<"$am_status"; then
    echo "observability-smoke failed: alertmanager config defines no receiver named ${receiver} (expected ibex-page for page, ibex-digest for ticket)"
    exit 1
  fi
done
echo "ok: alertmanager config shape (webhook_configs present, no local-null, ibex-page + ibex-digest defined)"
echo "note: deliverability not asserted; the base stack has no alert-receiver service (use make alert-delivery-test)"

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
