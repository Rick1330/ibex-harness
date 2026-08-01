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
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${CURL_MAX_TIME:-60}"
CURL_STREAM_MAX_TIME="${CURL_STREAM_MAX_TIME:-90}"

CHAT_BODY="$(printf '{"model":"%s","messages":[{"role":"user","content":"Reply with exactly: pong"}]}' "$LIVE_MODEL")"
STREAM_BODY="$(printf '{"model":"%s","stream":true,"messages":[{"role":"user","content":"Say hi in one word"}]}' "$LIVE_MODEL")"
HDR_CONTENT_TYPE_JSON="Content-Type: application/json"

fail() {
  local msg="$1"
  echo "FAIL: $msg" >&2
  exit 1
}

pass() {
  local msg="$1"
  echo "PASS: $msg"
}

expect_http() {
  local got="$1"
  local want="$2"
  local ok_msg="$3"
  local fail_msg="$4"
  if [[ "$got" == "$want" ]]; then
    pass "$ok_msg"
  else
    fail "$fail_msg"
  fi
}

http_code() {
  curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout "$CURL_CONNECT_TIMEOUT" \
    --max-time "$CURL_MAX_TIME" \
    "$@"
}

echo "=== IBEX Harness Live OpenRouter Smoke ==="
echo "  Proxy: $PROXY_ADDR"
echo "  Model: $LIVE_MODEL"
echo ""

if ! curl -s --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" \
  "$PROXY_ADDR/health" >/dev/null 2>&1; then
  fail "proxy not reachable at $PROXY_ADDR"
fi

HTTP="$(http_code "$PROXY_ADDR/health")"
expect_http "$HTTP" "200" "proxy /health → 200" "proxy /health returned $HTTP"

HTTP="$(http_code "$PROXY_ADDR/ready")"
expect_http "$HTTP" "200" "proxy /ready → 200" "proxy /ready returned $HTTP"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "$HDR_CONTENT_TYPE_JSON" \
  -d "$CHAT_BODY")"
expect_http "$HTTP" "401" "no token → 401" "no token returned $HTTP, want 401"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "$HDR_CONTENT_TYPE_JSON" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  -d '{"model":"not-a-real-model-xyz","messages":[{"role":"user","content":"x"}]}')"
expect_http "$HTTP" "501" "unknown model → 501" "unknown model returned $HTTP, want 501"

BODY_FILE="$(mktemp)"
HTTP="$(curl -s -o "$BODY_FILE" -w "%{http_code}" \
  --connect-timeout "$CURL_CONNECT_TIMEOUT" \
  --max-time "$CURL_MAX_TIME" \
  -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "$HDR_CONTENT_TYPE_JSON" \
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
HTTP="$(curl -s -o "$STREAM_FILE" -w "%{http_code}" -N \
  --connect-timeout "$CURL_CONNECT_TIMEOUT" \
  --max-time "$CURL_STREAM_MAX_TIME" \
  -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "$HDR_CONTENT_TYPE_JSON" \
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
expect_http "$HTTP" "200" "auth probe → 200" "auth probe returned $HTTP"

HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  "$PROXY_ADDR/v1/orgs/$DEV_ORG/auth-probe")"
expect_http "$HTTP" "200" "org auth probe → 200" "org auth probe returned $HTTP"

WRONG_ORG="00000000-0000-0000-0000-000000000099"
HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $DEV_AGENT" \
  "$PROXY_ADDR/v1/orgs/$WRONG_ORG/auth-probe")"
expect_http "$HTTP" "403" "cross-org path probe → 403" "cross-org probe returned $HTTP, want 403"

echo ""
echo "All live OpenRouter smoke tests passed"
