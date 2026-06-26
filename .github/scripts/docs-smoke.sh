#!/usr/bin/env bash
# Post-deploy smoke checks for the docs worker.
set -euo pipefail

BASE_URL="${1:?usage: docs-smoke.sh BASE_URL}"
BASE_URL="${BASE_URL%/}"

paths=(
  "/roadmap"
  "/roadmap/current-state"
  "/docs/getting-started/introduction"
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

echo "docs smoke passed (${#paths[@]} paths)"
