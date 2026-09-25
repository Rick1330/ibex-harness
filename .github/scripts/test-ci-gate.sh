#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="${ROOT}/.github/scripts/evaluate-ci-gate.sh"

expect_status() {
  local expected="$1" label="$2"
  shift 2
  local actual=0
  bash "$GATE" "$@" >/dev/null 2>&1 || actual=$?
  if [[ "$actual" -ne "$expected" ]]; then
    printf 'FAIL: %s: got exit %s, want %s\n' "$label" "$actual" "$expected" >&2
    exit 1
  fi
  printf 'PASS: %s\n' "$label"
}

# A deliberately inactive area is a passing no-op when change detection succeeded.
expect_status 0 "inactive area is a no-op" false success failure
# A missing or failed detector result must never be interpreted as an inactive path.
expect_status 1 "failed detector blocks inactive area" false failure
expect_status 1 "missing detector result blocks area" false "" success
# Scoped CI may legitimately skip unrelated jobs, but an active area must have
# at least one successful applicable child result.
expect_status 0 "active area with successful and skipped children" true success success skipped
expect_status 0 "active area with all successful children" true success success success
expect_status 1 "active area with failed child" true success success failure
expect_status 1 "active area with only skipped children" true success skipped skipped
expect_status 1 "active area with cancelled child" true success cancelled
expect_status 1 "active area with unknown child state" true success success pending
expect_status 1 "active area with no child results" true success

printf 'All CI gate regression cases passed.\n'
