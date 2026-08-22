#!/usr/bin/env bash
# Fail if scoped response-pipeline coverage is below MIN_COVERAGE (default 95).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=coverage-responsepipeline-gate_lib.sh
source "$ROOT/infra/scripts/coverage-responsepipeline-gate_lib.sh"

MIN_RAW="${MIN_COVERAGE:-95}"
validate_min_coverage "$MIN_RAW"
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
merge_scoped_profiles "$RP_PROFILE" "$BOOT_PROFILE" "$HTTP_PROFILE" "$FILTERED"

PCT=$(coverage_pct_from_profile "$FILTERED")
echo "response pipeline scoped coverage: ${PCT}% (minimum ${MIN}%)"
echo "  packages/responsepipeline"
echo "  services/proxy/internal/bootstrap/responsepipeline.go"
echo "  services/proxy/internal/http/chat_provider.go (processResponseBody path)"

check_coverage_threshold "$PCT" "$MIN"
