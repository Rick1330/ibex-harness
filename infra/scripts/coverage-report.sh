#!/usr/bin/env bash
# Generate merged unit + integration coverage report and gap summary.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

UNIT_OUT="${1:-coverage-go-unit.out}"
INT_OUT="${2:-coverage-go-integration.out}"
MERGED_OUT="${3:-coverage-go-merged.out}"

INTEGRATION_RAN=false

echo "==> Unit coverage"
go test -count=1 -coverprofile="$UNIT_OUT" \
  ./packages/... ./services/auth/... ./services/proxy/...

echo "==> Integration coverage (requires POSTGRES_TEST_DSN or compose-test)"
if [[ -z "${POSTGRES_TEST_DSN:-}" ]]; then
  echo "POSTGRES_TEST_DSN not set — skipping integration profile"
else
  go test -tags=integration -count=1 -p 1 -coverprofile="$INT_OUT" \
    ./packages/... ./services/auth/... ./services/proxy/... ./infra/...
  if command -v gocovmerge >/dev/null 2>&1; then
    gocovmerge "$UNIT_OUT" "$INT_OUT" > "$MERGED_OUT"
  else
    python3 "$ROOT/infra/scripts/gocovmerge.py" "$MERGED_OUT" "$UNIT_OUT" "$INT_OUT"
  fi
  INTEGRATION_RAN=true
  echo "Merged profile: $MERGED_OUT"
  go tool cover -func="$MERGED_OUT" | tail -1
fi

REPORT="${UNIT_OUT}"
if [[ "$INTEGRATION_RAN" == "true" && -f "$MERGED_OUT" ]]; then
  REPORT="$MERGED_OUT"
fi

echo ""
echo "==> Total (full profile)"
go tool cover -func="$REPORT" | tail -1

HANDWRITTEN="${REPORT%.out}-handwritten.out"
bash "$ROOT/infra/scripts/coverage-filter.sh" "$REPORT" "$HANDWRITTEN"
echo ""
echo "==> Hand-written (excludes packages/proto/gen/go)"
go tool cover -func="$HANDWRITTEN" | tail -1

echo ""
echo "==> Per-package (lowest 20)"
go tool cover -func="$REPORT" | grep -E 'packages/|services/' | grep -v 'total:' | \
  awk '{print $NF, $0}' | sort -n | head -20 | awk '{ $1=""; sub(/^ /,""); print }'

echo ""
echo "==> Top uncovered functions"
go tool cover -func="$REPORT" | grep -E '0\.0%|[1-9]\.[0-9]%' | grep -v 'total:' | head -50
