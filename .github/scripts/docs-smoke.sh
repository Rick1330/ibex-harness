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

# Cmd+K loads search-index URLs baked into HTML/JS; every referenced file must exist.
mapfile -t baked_paths < <(
  curl -fsS "${BASE_URL}/roadmap" \
    | grep -oE '/search-index[^"'"'"' )>]+\.json' \
    | sort -u
)
if [[ "${#baked_paths[@]}" -eq 0 ]]; then
  echo "smoke failed: no search-index URL found in /roadmap HTML"
  exit 1
fi
for path in "${baked_paths[@]}"; do
  url="${BASE_URL}${path}"
  code="$(curl -fsS -o /dev/null -w '%{http_code}' "$url" || true)"
  if [[ "$code" != "200" ]]; then
    echo "smoke failed: baked search index $url returned HTTP $code"
    exit 1
  fi
  echo "ok: baked search index $path"
done

# Production must be Pages static CDN, not the legacy OpenNext Worker.
intro_headers="$(curl -fsSI "${BASE_URL}/docs/getting-started/introduction" || true)"
if echo "$intro_headers" | grep -qi 'x-opennext'; then
  echo "smoke failed: ${BASE_URL} still served by OpenNext Worker (x-opennext header)"
  exit 1
fi
echo "ok: not served by OpenNext Worker"

echo "docs smoke passed (${#paths[@]} paths + search size + redirect + baked index + host)"
