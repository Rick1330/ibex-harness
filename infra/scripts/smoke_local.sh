#!/usr/bin/env bash
# infra/scripts/smoke_local.sh
# Local development smoke test: validates auth+proxy pipeline without an LLM key.
# Usage: make dev-smoke
# Prerequisites: make compose-dev-up && make db-migrate && make db-seed
#                auth and proxy services running locally

set -euo pipefail

PROXY_ADDR="${IBEX_PROXY_ADDR:-http://localhost:8080}"
DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
DEV_AGENT="${IBEX_DEV_AGENT_ID:-00000000-0000-0000-0000-000000000003}"
DEV_ORG="${IBEX_DEV_ORG_ID:-00000000-0000-0000-0000-000000000001}"

CHAT_BODY='{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}'

fail() { echo "FAIL: $1" >&2; exit 1; }
pass() { echo "PASS: $1"; }

http_code() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

echo "=== IBEX Harness Local Smoke Test ==="
echo "  Proxy: $PROXY_ADDR"
echo ""

if ! curl -s --connect-timeout 2 "$PROXY_ADDR/health" >/dev/null 2>&1; then
  echo "Prerequisites:"
  echo "  make compose-dev-up"
  echo "  make db-migrate"
  echo "  make db-seed"
  echo "  # Start auth and proxy (see README Quick Start)"
  fail "proxy not reachable at $PROXY_ADDR"
fi

HTTP="$(http_code "$PROXY_ADDR/health")"
[[ "$HTTP" == "200" ]] && pass "proxy /health → 200" || fail "proxy /health returned $HTTP"

HTTP="$(http_code "$PROXY_ADDR/ready")"
[[ "$HTTP" == "200" ]] && pass "proxy /ready → 200" || fail "proxy /ready returned $HTTP"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "$CHAT_BODY")"
[[ "$HTTP" == "401" ]] && pass "no token → 401" || fail "no token returned $HTTP, want 401"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -d "$CHAT_BODY")"
[[ "$HTTP" == "400" ]] && pass "missing agent → 400" || fail "missing agent returned $HTTP, want 400"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  -d "$CHAT_BODY")"
[[ "$HTTP" == "501" ]] && pass "valid request → 501 (expected: no upstream LLM)" \
  || fail "valid chat returned $HTTP, want 501 PROVIDER_NOT_CONFIGURED"

HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  "$PROXY_ADDR/v1/internal/auth-probe")"
[[ "$HTTP" == "200" ]] && pass "auth probe → 200" || fail "auth probe returned $HTTP"

HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  "$PROXY_ADDR/v1/orgs/$DEV_ORG/auth-probe")"
[[ "$HTTP" == "200" ]] && pass "org-scoped auth probe → 200" || fail "org auth probe returned $HTTP"

GOT_429=0
for _ in $(seq 1 65); do
  HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
    -H "Authorization: Bearer $DEV_TOKEN" \
    -H "X-IBEX-Agent-ID: $DEV_AGENT" \
    -H "Content-Type: application/json" \
    -d "$CHAT_BODY" 2>/dev/null || true)"
  if [[ "$HTTP" == "429" ]]; then
    GOT_429=1
    break
  fi
done
if [[ "$GOT_429" == "1" ]]; then
  pass "rate limit enforcement → at least one 429"
else
  echo "WARN: 65 requests did not produce a 429 (check IBEX_RATE_LIMIT_DEFAULT_RPM)"
fi

echo ""
echo "All smoke tests passed"
