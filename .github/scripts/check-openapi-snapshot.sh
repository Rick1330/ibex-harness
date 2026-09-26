#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
(cd "$ROOT/services/api" && uv run python scripts/export_openapi.py "$TMP" >/dev/null)
if ! cmp -s "$TMP" "$ROOT/services/api/openapi.snapshot.json"; then
  echo 'OpenAPI snapshot is stale; run services/api/scripts/export_openapi.py services/api/openapi.snapshot.json' >&2
  diff -u "$ROOT/services/api/openapi.snapshot.json" "$TMP" || true
  exit 1
fi
echo 'OpenAPI snapshot is fresh'
