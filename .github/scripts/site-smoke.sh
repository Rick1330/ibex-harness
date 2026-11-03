#!/usr/bin/env bash
# Post-deploy smoke checks for the Docus site (Cloudflare Pages).
set -euo pipefail

BASE_URL="${1:?usage: site-smoke.sh BASE_URL}"
BASE_URL="${BASE_URL%/}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-10}"
CURL_MAX_TIME="${CURL_MAX_TIME:-30}"

curl_smoke() {
  curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" "$@"
}

paths=(
  "/"
  "/benchmarks"
  "/releases"
  "/blog"
  "/blog/proxy-before-memory"
  "/blog/memory-write-path"
  "/blog/context-assembly-budget"
  "/docs"
  "/docs/getting-started/introduction"
  "/docs/getting-started/concepts"
  "/docs/architecture/status-and-evidence"
  "/docs/architecture/overview"
  "/docs/architecture/services"
  "/docs/deployment"
  "/ai.txt"
  "/llms.txt"
  "/sitemap.xml"
  "/releases.xml"
)

for path in "${paths[@]}"; do
  url="${BASE_URL}${path}"
  code="$(curl_smoke -o /dev/null -w '%{http_code}' "$url" || true)"
  if [[ "$code" != "200" ]]; then
    echo "smoke failed: $url returned HTTP $code"
    exit 1
  fi
  echo "ok: $url"
done

home="$(curl_smoke "${BASE_URL}/")"
if ! grep -qF 'Memory for agents.' <<<"$home" || ! grep -qF 'Control for you.' <<<"$home"; then
  echo "smoke failed: / does not include the current landing headline"
  exit 1
fi
echo "ok: / includes the current landing headline"

status_page="$(curl_smoke "${BASE_URL}/docs/architecture/status-and-evidence")"
if ! grep -qi 'not.*production' <<<"$status_page"; then
  echo "smoke failed: status page is missing the production-claim boundary"
  exit 1
fi
echo "ok: status page keeps the production boundary"

headers="$(curl_smoke -I "${BASE_URL}/")"
for header in 'x-content-type-options: nosniff' 'x-frame-options: deny' 'content-security-policy:'; do
  if ! grep -qi "$header" <<<"$headers"; then
    echo "smoke failed: missing header $header"
    exit 1
  fi
done
echo "ok: security headers present"

for legacy in "/status" "/roadmap" "/docs/agents" "/blog/phase-1-launch" "/blog/ibex-memory-lifecycle-map"; do
  redirect_code="$(curl_smoke -o /dev/null -w '%{http_code}' "${BASE_URL}${legacy}" || true)"
  if [[ "$redirect_code" != "301" && "$redirect_code" != "302" && "$redirect_code" != "308" ]]; then
    echo "smoke failed: ${legacy} redirect returned HTTP $redirect_code"
    exit 1
  fi
  final_code="$(curl_smoke -L -o /dev/null -w '%{http_code}' "${BASE_URL}${legacy}" || true)"
  if [[ "$final_code" != "200" ]]; then
    echo "smoke failed: ${legacy} redirect ended at HTTP $final_code instead of 200"
    exit 1
  fi
  echo "ok: ${legacy} redirects to HTTP 200 (${redirect_code})"
done

echo "site smoke passed (${#paths[@]} paths + content + headers + redirects)"
