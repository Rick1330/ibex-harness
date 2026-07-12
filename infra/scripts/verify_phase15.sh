#!/usr/bin/env bash
# Phase 1.5 launch verification for the unified public site (landing, docs,
# benchmarks, blog, releases, roadmap). Wraps web-smoke.sh and adds D.5.2
# acceptance checks from MASTER_BRIEF adapted for the ibexharness.com layout.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="${IBEX_SITE_URL:-${IBEX_DOCS_URL:-https://ibexharness.com}}"
BASE="${BASE%/}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-10}"
CURL_MAX_TIME="${CURL_MAX_TIME:-30}"

echo "verify_phase15: checking $BASE"

bash "$ROOT_DIR/.github/scripts/web-smoke.sh" "$BASE"

check_200() {
  local path="$1"
  local url="${BASE}${path}"
  local code
  code="$(curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" \
    -o /dev/null -w '%{http_code}' "$url" || true)"
  if [[ "$code" != "200" ]]; then
    echo "verify_phase15 failed: $url returned HTTP $code (expected 200)"
    exit 1
  fi
  echo "ok: $url"
}

for path in \
  /docs/getting-started/quickstart \
  /docs/proxy/overview \
  /docs/api-reference/chat-completions \
  /docs/changelog \
  /blog \
  /releases \
  /robots.txt \
  /sitemap.xml; do
  check_200 "$path"
done

not_found_code="$(curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" \
  -o /dev/null -w '%{http_code}' "${BASE}/docs/this-does-not-exist" || true)"
if [[ "$not_found_code" != "404" ]]; then
  echo "verify_phase15 failed: missing doc page returned HTTP $not_found_code (expected 404)"
  exit 1
fi
echo "ok: /docs/this-does-not-exist returns 404"

og_headers="$(curl -fsSI --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" \
  "${BASE}/docs/getting-started/introduction/opengraph-image.png" || true)"
if ! grep -qi '^content-type: image/png' <<<"$og_headers"; then
  echo "verify_phase15 failed: OG image missing image/png content-type"
  exit 1
fi
echo "ok: OG image content-type image/png"

echo "Phase 1.5 verification passed ($BASE)"
