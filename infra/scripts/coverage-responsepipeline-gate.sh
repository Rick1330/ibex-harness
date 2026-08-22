#!/usr/bin/env bash
# Fail if scoped response-pipeline coverage is below MIN_COVERAGE (default 95).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIN_RAW="${MIN_COVERAGE:-95}"
if ! [[ "$MIN_RAW" =~ ^[0-9]+$ ]]; then
  echo "MIN_COVERAGE must be an integer, got: $MIN_RAW"
  exit 1
fi
MIN="$MIN_RAW"

cd "$ROOT"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

RP_PROFILE="$TMPDIR/responsepipeline.out"
BOOT_PROFILE="$TMPDIR/bootstrap.out"
HTTP_PROFILE="$TMPDIR/http.out"

go test -count=1 -coverprofile="$RP_PROFILE" ./packages/responsepipeline/...
go test -count=1 -coverprofile="$BOOT_PROFILE" ./services/proxy/internal/bootstrap/...
go test -count=1 -coverprofile="$HTTP_PROFILE" ./services/proxy/internal/http/...

FILTERED="$TMPDIR/scoped.out"
{
  grep -E '^mode:' "$RP_PROFILE"
  grep -vE '^mode:' "$RP_PROFILE"
  grep -vE '^mode:' "$BOOT_PROFILE" | grep 'responsepipeline\.go'
  grep -vE '^mode:' "$HTTP_PROFILE" | grep 'chat_provider\.go' | awk -F: '$2 >= 149 && $2 <= 174 { print }'
} > "$FILTERED"

PCT=$(go tool cover -func="$FILTERED" | awk '/^total:/ { gsub(/%/,"",$3); print $3 }')
echo "response pipeline scoped coverage: ${PCT}% (minimum ${MIN}%)"
echo "  packages/responsepipeline"
echo "  services/proxy/internal/bootstrap/responsepipeline.go"
echo "  services/proxy/internal/http/chat_provider.go (processResponseBody path)"

awk -v pct="$PCT" -v min="$MIN" 'BEGIN { exit (pct + 0 >= min + 0) ? 0 : 1 }'
