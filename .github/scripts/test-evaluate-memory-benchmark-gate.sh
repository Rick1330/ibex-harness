#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="${ROOT}/.github/scripts/evaluate-memory-benchmark-gate.sh"

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

# Not due: the collectors are skipped by design, so their results are ignored.
expect_status 0 "inactive paths pass with skipped collectors" false success skipped skipped skipped
expect_status 0 "inactive paths pass with no collector results" false success
# A failed or missing detector must never be read as "not due".
expect_status 1 "failed detector blocks the gate" false failure
expect_status 1 "missing detector result blocks the gate" false "" success
expect_status 2 "invalid bench_active is a usage error" maybe success success
# Due: every collector must have run and passed. Unlike the general CI gate, `skipped`
# is not acceptable -- it means a due collector did not run.
expect_status 0 "all collectors successful" true success success success success
expect_status 1 "skipped collector blocks when due" true success success skipped success
expect_status 1 "failed collector blocks when due" true success success failure success
expect_status 1 "cancelled collector blocks when due" true success cancelled success success
expect_status 1 "unknown collector state blocks when due" true success success pending success
expect_status 1 "no collector results blocks when due" true success

printf 'All memory benchmark gate regression cases passed.\n'
