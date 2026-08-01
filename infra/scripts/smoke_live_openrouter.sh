#!/usr/bin/env bash
# infra/scripts/smoke_live_openrouter.sh
# Live OpenRouter smoke: real auth+proxy+upstream (not mockllm).
# Prerequisites: compose-dev-up, db-migrate, db-seed, auth+proxy running with:
#   IBEX_LLM_MODE=live
#   OPENAI_BASE_URL=https://openrouter.ai/api/v1
#   OPENAI_API_KEY=<from ibex-open-ai-token/open-ai-token-open-router.env>
#   IBEX_LLM_EXTRA_MODELS=openai/gpt-oss-20b:free
#   IBEX_AUTH_VALIDATE_TIMEOUT=2s
# Usage: make dev-smoke-live
#        or: bash infra/scripts/smoke_live_openrouter.sh

set -euo pipefail

PROXY_ADDR="${IBEX_PROXY_ADDR:-http://localhost:8080}"
DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
DEV_AGENT="${IBEX_DEV_AGENT_ID:-00000000-0000-0000-0000-000000000003}"
DEV_ORG="${IBEX_DEV_ORG_ID:-00000000-0000-0000-0000-000000000001}"
LIVE_MODEL="${IBEX_LIVE_MODEL:-openai/gpt-oss-20b:free}"

CHAT_BODY="$(printf '{"model":"%s","messages":[{"role":"user","content":"Reply with exactly: pong"}]}' "$LIVE_MODEL")"
STREAM_BODY="$(printf '{"model":"%s","stream":true,"messages":[{"role":"user","content":"Say hi in one word"}]}' "$LIVE_MODEL")"

fail() { echo "FAIL: $1" >&2; exit 1; }
pass() { echo "PASS: $1"; }

http_code() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

echo "=== IBEX Harness Live OpenRouter Smoke ==="
echo "  Proxy: $PROXY_ADDR"
echo "  Model: $LIVE_MODEL"
echo ""

if ! curl -s --connect-timeout 2 "$PROXY_ADDR/health" >/dev/null 2>&1; then
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
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  -d '{"model":"not-a-real-model-xyz","messages":[{"role":"user","content":"x"}]}')"
[[ "$HTTP" == "501" ]] && pass "unknown model → 501" || fail "unknown model returned $HTTP, want 501"

BODY_FILE="$(mktemp)"
HTTP="$(curl -s -o "$BODY_FILE" -w "%{http_code}" -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  -d "$CHAT_BODY")"
if [[ "$HTTP" != "200" ]]; then
  echo "body: $(head -c 500 "$BODY_FILE")" >&2
  rm -f "$BODY_FILE"
  fail "live chat returned $HTTP, want 200"
fi
if ! grep -q 'choices' "$BODY_FILE"; then
  echo "body: $(head -c 500 "$BODY_FILE")" >&2
  rm -f "$BODY_FILE"
  fail "live chat body missing choices"
fi
rm -f "$BODY_FILE"
pass "live chat → 200 with choices"

STREAM_FILE="$(mktemp)"
HTTP="$(curl -s -o "$STREAM_FILE" -w "%{http_code}" -N -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  -d "$STREAM_BODY")"
if [[ "$HTTP" != "200" ]]; then
  echo "stream body: $(head -c 500 "$STREAM_FILE")" >&2
  rm -f "$STREAM_FILE"
  fail "live stream returned $HTTP, want 200"
fi
if ! grep -q 'data:' "$STREAM_FILE"; then
  echo "stream body: $(head -c 500 "$STREAM_FILE")" >&2
  rm -f "$STREAM_FILE"
  fail "live stream missing SSE data lines"
fi
rm -f "$STREAM_FILE"
pass "live stream → 200 SSE"

HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  "$PROXY_ADDR/v1/internal/auth-probe")"
[[ "$HTTP" == "200" ]] && pass "auth probe → 200" || fail "auth probe returned $HTTP"

HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  "$PROXY_ADDR/v1/orgs/$DEV_ORG/auth-probe")"
[[ "$HTTP" == "200" ]] && pass "org auth probe → 200" || fail "org auth probe returned $HTTP"

WRONG_ORG="00000000-0000-0000-0000-000000000099"
HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  "$PROXY_ADDR/v1/orgs/$WRONG_ORG/auth-probe")"
[[ "$HTTP" == "403" ]] && pass "cross-org path probe → 403" || fail "cross-org probe returned $HTTP, want 403"

echo ""
echo "All live OpenRouter smoke tests passed"
