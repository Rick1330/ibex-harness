#!/usr/bin/env bash
# Guard tests for the bundle smoke's loopback-only URL check.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT_DIR/infra/scripts/bundle-smoke.sh"
fail=0

expect_ok() {
  if BUNDLE_MEMORY_URL="$1" bash "$SCRIPT" --check-url >/dev/null 2>&1; then
    echo "PASS: accepts $1"
  else
    echo "FAIL: should accept $1" >&2
    fail=1
  fi
}

expect_reject() {
  if BUNDLE_MEMORY_URL="$1" bash "$SCRIPT" --check-url >/dev/null 2>&1; then
    echo "FAIL: should reject $1" >&2
    fail=1
  else
    echo "PASS: rejects $1"
  fi
}

expect_ok "http://127.0.0.1:18005"
expect_ok "http://localhost:18005"
expect_ok "http://[::1]:18005"

# User information can hide a remote host from a naive prefix check.
expect_reject "http://127.0.0.1:18005@example.com"
expect_reject "http://0.0.0.0:18005"
expect_reject "https://127.0.0.1:18005"
expect_reject "http://127.0.0.1"

if ((fail != 0)); then
  echo "bundle smoke URL guard tests failed" >&2
  exit 1
fi

echo "bundle smoke URL guard tests passed"
