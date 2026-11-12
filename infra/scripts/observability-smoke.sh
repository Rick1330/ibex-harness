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
if grep -q 'local-null' <<<"$am_status"; then
  echo "observability-smoke failed: alertmanager still routes to the null receiver (local-null)"
  exit 1
fi

# A webhook shape check passes for any receiver, and one global grep for
# `webhook_configs` lets an ibex-page webhook satisfy the check for ibex-digest.
# Receiver names are checked per receiver, so a renamed or dropped receiver is
# caught here instead of surfacing as an alert that was never sent.
ALERT_RECEIVERS=(ibex-page ibex-digest)

# Print one line per receiver in $1 that cannot deliver, and exit 1 when there
# is one. Alertmanager serialises the served config into the JSON string
# `.config.original` (escaped `\n`, URLs redacted to `<secret>`), so decode it,
# split it into receiver blocks, and require each named receiver to own a
# `webhook_configs:` entry. The URL itself cannot be checked here: the served
# copy redacts it, and this is a shape check, not a delivery check.
# python3 parses the JSON because it is already required by `make repo-guards`
# (check-alert-routing.py) and by the sibling observability-live-verify.sh; jq is
# not used by any other infra/scripts/*.sh. A missing python3 fails closed below.
alertmanager_receiver_problems() {
  AM_STATUS_TEXT="$1" python3 - "${ALERT_RECEIVERS[@]}" <<'PY'
"""Require each named Alertmanager receiver to carry its own webhook_configs."""
import json
import os
import re
import sys

ITEM_RE = re.compile(r"^- name:\s*(?P<name>.+?)\s*$")


def receiver_blocks(config):
    """Map receiver name -> the stripped body lines of that receiver.

    Handles both shapes: the committed file indents the sequence under
    `receivers:`, while Alertmanager re-serialises it with `- name:` at the
    same column as the key.
    """
    blocks = {}
    in_receivers = False
    item_indent = None
    current = None
    for raw in config.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0 and not stripped.startswith("-"):
            # A top-level key; only `receivers:` opens the block read here.
            in_receivers = stripped.startswith("receivers:")
            item_indent, current = None, None
            continue
        if not in_receivers:
            continue
        item = ITEM_RE.match(stripped)
        if item is not None and (item_indent is None or indent <= item_indent):
            item_indent = indent
            current = item.group("name").strip("'\"")
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append(stripped)
    return blocks


def config_text(status_text):
    """The served config, or None when the status body does not carry it."""
    try:
        status = json.loads(status_text)
    except json.JSONDecodeError:
        return None
    config = status.get("config") if isinstance(status, dict) else None
    original = config.get("original") if isinstance(config, dict) else None
    return original if isinstance(original, str) and original.strip() else None


def receiver_problems(required, blocks):
    """One line per required receiver that is missing or has no webhook_configs."""
    problems = []
    for name in required:
        block = blocks.get(name)
        if block is None:
            problems.append(
                f"alertmanager config defines no receiver named {name} "
                "(expected ibex-page for page, ibex-digest for ticket)"
            )
        elif not any(line.startswith("webhook_configs:") for line in block):
            problems.append(
                f"receiver {name} has no webhook_configs of its own (its alerts would be dropped)"
            )
    return problems


served = config_text(os.environ.get("AM_STATUS_TEXT", ""))
if served is None:
    print("could not read .config.original from /api/v2/status")
    sys.exit(1)
found = receiver_problems(sys.argv[1:], receiver_blocks(served))
for problem in found:
    print(problem)
sys.exit(1 if found else 0)
PY
}

if ! am_problems="$(alertmanager_receiver_problems "$am_status")"; then
  while IFS= read -r problem; do
    if [[ -n "$problem" ]]; then
      echo "observability-smoke failed: $problem" >&2
    fi
  done <<<"$am_problems"
  if [[ -z "$am_problems" ]]; then
    echo "observability-smoke failed: could not check the served alertmanager config (see the error above)" >&2
  fi
  exit 1
fi
echo "ok: alertmanager config shape (no local-null, ibex-page + ibex-digest each carry webhook_configs)"
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
