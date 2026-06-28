#!/usr/bin/env bash
# Post-deploy smoke checks for the docs site (Cloudflare Pages).
set -euo pipefail

BASE_URL="${1:?usage: docs-smoke.sh BASE_URL}"
BASE_URL="${BASE_URL%/}"
SEARCH_INDEX_MAX_BYTES="${SEARCH_INDEX_MAX_BYTES:-5000000}"

paths=(
  "/roadmap"
  "/roadmap/current-state"
  "/docs/getting-started/introduction"
  "/docs/getting-started/introduction/opengraph-image.png"
  "/search-index.json"
)

for path in "${paths[@]}"; do
  url="${BASE_URL}${path}"
  code="$(curl -fsS -o /dev/null -w '%{http_code}' "$url" || true)"
  if [ "$code" != "200" ]; then
    echo "smoke failed: $url returned HTTP $code"
    exit 1
  fi
  echo "ok: $url"
done

search_url="${BASE_URL}/search-index.json"
size="$(curl -fsS "$search_url" | wc -c | tr -d ' ')"
if [[ "$size" -gt "$SEARCH_INDEX_MAX_BYTES" ]]; then
  echo "smoke failed: $search_url is ${size} bytes (max ${SEARCH_INDEX_MAX_BYTES})"
  exit 1
fi
echo "ok: search index size ${size} bytes (max ${SEARCH_INDEX_MAX_BYTES})"

redirect_code="$(curl -fsS -o /dev/null -w '%{http_code}' "${BASE_URL}/api/search" || true)"
if [[ "$redirect_code" != "308" && "$redirect_code" != "301" && "$redirect_code" != "302" ]]; then
  echo "smoke failed: /api/search redirect returned HTTP $redirect_code"
  exit 1
fi
echo "ok: /api/search redirects (${redirect_code})"

echo "docs smoke passed (${#paths[@]} paths + search size + redirect)"
