#!/usr/bin/env bash
# Run hierarchical rate-limit integration tests against real Redis and fail if skipped.
# Usage: REDIS_URL=redis://127.0.0.1:6379/14 bash infra/scripts/ratelimit-hierarchical-integration-ci.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/14}"
export REDIS_URL

# Fail closed before go test: unreachable Redis must not become a silent skip.
python3 - <<'PY'
import os, socket, sys, urllib.parse

raw = os.environ.get("REDIS_URL", "")
u = urllib.parse.urlparse(raw)
if u.scheme not in ("redis", "rediss") or not u.hostname:
    print(f"invalid REDIS_URL for hierarchical gate: {raw!r}", file=sys.stderr)
    sys.exit(1)
port = u.port or 6379
path = (u.path or "/0").lstrip("/")
db = int(path.split("/")[0] or "0")
if db != 14:
    print(f"REDIS_URL must use DB 14 for hierarchical gate (got {db})", file=sys.stderr)
    sys.exit(1)

# Minimal RESP PING (no redis-py dependency).
try:
    with socket.create_connection((u.hostname, port), timeout=2.0) as s:
        s.sendall(b"*1\r\n$4\r\nPING\r\n")
        resp = s.recv(64)
except OSError as e:
    print(f"Redis unreachable at {u.hostname}:{port}: {e}", file=sys.stderr)
    sys.exit(1)
if not resp.startswith(b"+PONG"):
    print(f"unexpected Redis PING response: {resp!r}", file=sys.stderr)
    sys.exit(1)
print(f"Redis OK {u.hostname}:{port}/{db}")
PY

LOG="$(mktemp)"
# shellcheck disable=SC2329 # invoked via trap EXIT
cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

set +e
bash infra/scripts/go-test-gotestsum.sh test-results/junit/ratelimit-hierarchical-integration.xml -- \
  -race -tags=integration -timeout=120s -count=1 \
  -run '^TestIntegration_Hierarchical' ./packages/ratelimit/... \
  2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}
set -e

if grep -E -- '--- SKIP: TestIntegration_Hierarchical' "$LOG" >/dev/null; then
  echo "hierarchical integration tests must not skip when Redis is required" >&2
  exit 1
fi
if ! grep -E -- '--- PASS: TestIntegration_Hierarchical_ZeroOverAdmission_200x100( |$)' "$LOG" >/dev/null; then
  echo "expected PASS for TestIntegration_Hierarchical_ZeroOverAdmission_200x100" >&2
  exit 1
fi
if ! grep -E -- '--- PASS: TestIntegration_Hierarchical_sameAgentDifferentOrgsIndependent( |$)' "$LOG" >/dev/null; then
  echo "expected PASS for TestIntegration_Hierarchical_sameAgentDifferentOrgsIndependent" >&2
  exit 1
fi
if ! grep -E -- 'admitted=100 rejected=100' "$LOG" >/dev/null; then
  echo "expected logged exact 100/100 admit/reject counts" >&2
  exit 1
fi

exit "$status"
