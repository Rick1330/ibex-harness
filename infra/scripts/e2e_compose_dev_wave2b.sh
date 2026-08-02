#!/usr/bin/env bash
# Full compose-dev E2E for Wave 2b token composite org FKs + CreateToken binds.
# Prerequisites: compose-dev up, db-migrate, db-seed; auth (:9091) and proxy (:8080) running.
# Usage: bash infra/scripts/e2e_compose_dev_wave2b.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POSTGRES_USER="${POSTGRES_USER:-ibex}"
POSTGRES_DB="${POSTGRES_DB:-ibex}"
ORG_A="00000000-0000-0000-0000-000000000001"
USER_A="00000000-0000-0000-0000-000000000002"
AGENT_A="00000000-0000-0000-0000-000000000003"
DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
PROXY_ADDR="${IBEX_PROXY_ADDR:-http://localhost:8080}"
AUTH_HTTP="${IBEX_AUTH_HTTP:-http://localhost:8081}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

run_psql() {
  if command -v psql >/dev/null 2>&1; then
    local dsn="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
    dsn="${dsn//postgresql+asyncpg:/postgres:}"
    dsn="${dsn//postgresql:/postgres:}"
    psql "$dsn" -v ON_ERROR_STOP=1 "$@"
    return
  fi
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ibex-dev-postgres; then
    docker exec -i ibex-dev-postgres \
      psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"
    return
  fi
  fail "need psql or running ibex-dev-postgres"
}

echo "=== Wave 2b compose-dev E2E ==="

# ── 1. Migration / constraint inventory ─────────────────────────────────────
VER="$(run_psql -Atc "SELECT version FROM schema_migrations LIMIT 1" | tr -d '\r')"
DIRTY="$(run_psql -Atc "SELECT dirty::text FROM schema_migrations LIMIT 1" | tr -d '\r')"
[[ "$VER" == "12" ]] || fail "schema_migrations version=$VER want 12"
[[ "$DIRTY" == "f" || "$DIRTY" == "false" ]] || fail "schema_migrations dirty=$DIRTY"
pass "migrate version=12 dirty=false"

for c in tokens_agent_org_fk tokens_user_org_fk tokens_revoked_by_fk; do
  ok="$(run_psql -Atc "SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = '$c' AND conrelid = 'ibex_core.tokens'::regclass
  )" | tr -d '\r')"
  [[ "$ok" == "t" ]] || fail "missing constraint $c"
done
pass "tokens composite subject FKs + revoked_by present"

for c in tokens_agent_id_fk tokens_user_id_fk; do
  ok="$(run_psql -Atc "SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = '$c' AND conrelid = 'ibex_core.tokens'::regclass
  )" | tr -d '\r')"
  [[ "$ok" == "f" ]] || fail "legacy constraint $c still present"
done
pass "legacy single-column subject FKs absent"

ok="$(run_psql -Atc "SELECT EXISTS (
  SELECT 1 FROM pg_constraint
  WHERE conname = 'users_id_org_unique' AND conrelid = 'ibex_core.users'::regclass
)" | tr -d '\r')"
[[ "$ok" == "t" ]] || fail "missing users_id_org_unique"
pass "users_id_org_unique present"

# ── 2. Seed second org for cross-org cases ──────────────────────────────────
run_psql <<'SQL'
SELECT set_config('app.is_service_account', 'true', true);

INSERT INTO ibex_core.organizations (id, name, slug, tier, status)
VALUES (
  '00000000-0000-0000-0000-0000000000b1',
  'IBEX E2E Org B', 'ibex-e2e-b', 'free', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.users (id, org_id, email, name, role, status)
VALUES (
  '00000000-0000-0000-0000-0000000000b2',
  '00000000-0000-0000-0000-0000000000b1',
  'e2e-b@ibex.local', 'E2E User B', 'owner', 'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
VALUES (
  '00000000-0000-0000-0000-0000000000b3',
  '00000000-0000-0000-0000-0000000000b1',
  '00000000-0000-0000-0000-0000000000b2',
  'E2E Agent B', 'e2e-agent-b', 'active'
) ON CONFLICT (id) DO NOTHING;
SQL
USER_B="00000000-0000-0000-0000-0000000000b2"
AGENT_B="00000000-0000-0000-0000-0000000000b3"
pass "seeded org B user/agent for cross-org probes"

# ── 3. SQL edge matrix (defense-in-depth FKs) ───────────────────────────────
assert_sql_fail() {
  local label="$1"
  local sql="$2"
  if run_psql <<SQL >/dev/null 2>&1
SELECT set_config('app.is_service_account', 'true', true);
$sql
SQL
  then
    fail "SQL expected fail: $label"
  fi
  pass "SQL deny: $label"
}

assert_sql_ok() {
  local label="$1"
  local sql="$2"
  run_psql <<SQL >/dev/null
SELECT set_config('app.is_service_account', 'true', true);
$sql
SQL
  pass "SQL allow: $label"
}

H="e2e_$(date +%s)_$RANDOM"
assert_sql_fail "cross-org agent_id" \
  "INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, agent_id)
   VALUES ('$ORG_A'::uuid, 'pat', 'h_${H}_xa', 'ibex_pat_xa', 'cross-agent', 0, '$AGENT_B'::uuid);"

assert_sql_fail "cross-org user_id" \
  "INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, user_id)
   VALUES ('$ORG_A'::uuid, 'pat', 'h_${H}_xu', 'ibex_pat_xu', 'cross-user', 0, '$USER_B'::uuid);"

assert_sql_ok "same-org agent_id" \
  "INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, agent_id)
   VALUES ('$ORG_A'::uuid, 'pat', 'h_${H}_sa', 'ibex_pat_sa', 'same-agent', 0, '$AGENT_A'::uuid);"

assert_sql_ok "same-org user_id" \
  "INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, user_id)
   VALUES ('$ORG_A'::uuid, 'pat', 'h_${H}_su', 'ibex_pat_su', 'same-user', 0, '$USER_A'::uuid);"

assert_sql_ok "NULL subjects (MATCH SIMPLE)" \
  "INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions)
   VALUES ('$ORG_A'::uuid, 'pat', 'h_${H}_null', 'ibex_pat_nl', 'null-subjects', 0);"

assert_sql_ok "cross-org revoked_by (intentional single-column FK)" \
  "INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, is_revoked, revoked_by)
   VALUES ('$ORG_A'::uuid, 'pat', 'h_${H}_rb', 'ibex_pat_rb', 'cross-revoked-by', 0, true, '$USER_B'::uuid);"

assert_sql_fail "nonexistent agent_id" \
  "INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, agent_id)
   VALUES ('$ORG_A'::uuid, 'pat', 'h_${H}_miss', 'ibex_pat_ms', 'missing-agent', 0,
           '00000000-0000-0000-0000-00000000dead'::uuid);"

# ── 4. Service readiness ────────────────────────────────────────────────────
curl -sf --connect-timeout 2 "$AUTH_HTTP/health" >/dev/null || fail "auth HTTP not up at $AUTH_HTTP"
curl -sf --connect-timeout 2 "$AUTH_HTTP/ready" >/dev/null || fail "auth not ready"
pass "auth /health + /ready"

curl -sf --connect-timeout 2 "$PROXY_ADDR/health" >/dev/null || fail "proxy not up at $PROXY_ADDR"
curl -sf --connect-timeout 2 "$PROXY_ADDR/ready" >/dev/null || fail "proxy not ready"
pass "proxy /health + /ready"

# ── 5. CreateToken gRPC matrix against live auth ────────────────────────────
export IBEX_E2E_USER_B="$USER_B"
export IBEX_E2E_AGENT_B="$AGENT_B"
export IBEX_DEV_TOKEN="$DEV_TOKEN"
export IBEX_DEV_ORG_ID="$ORG_A"
export IBEX_DEV_USER_ID="$USER_A"
export IBEX_DEV_AGENT_ID="$AGENT_A"
export IBEX_AUTH_GRPC_ADDR="${IBEX_AUTH_GRPC_ADDR:-127.0.0.1:9091}"
(cd "$ROOT_DIR" && go run ./infra/scripts/cmd/e2e-token-fks)

# ── 6. Proxy edge cases (real auth path) ────────────────────────────────────
http_code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
CHAT='{"model":"gpt-4o","messages":[{"role":"user","content":"e2e"}]}'

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" -d "$CHAT")"
[[ "$HTTP" == "401" ]] || fail "no token → want 401 got $HTTP"
pass "proxy no token → 401"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer not-a-real-token" \
  -d "$CHAT")"
[[ "$HTTP" == "401" ]] || fail "bad token → want 401 got $HTTP"
pass "proxy bad token → 401"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -d "$CHAT")"
[[ "$HTTP" == "400" ]] || fail "missing agent → want 400 got $HTTP"
pass "proxy missing agent → 400"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $AGENT_B" \
  -d "$CHAT")"
[[ "$HTTP" == "403" ]] || fail "cross-org agent → want 403 got $HTTP"
pass "proxy cross-org agent → 403"

HTTP="$(http_code -X POST "$PROXY_ADDR/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $AGENT_A" \
  -d "$CHAT")"
[[ "$HTTP" == "200" ]] || fail "valid mock chat → want 200 got $HTTP"
pass "proxy valid chat (mock) → 200"

HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $AGENT_A" \
  "$PROXY_ADDR/v1/internal/auth-probe")"
[[ "$HTTP" == "200" ]] || fail "auth-probe → want 200 got $HTTP"
pass "proxy auth-probe → 200"

HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $AGENT_A" \
  "$PROXY_ADDR/v1/orgs/$ORG_A/auth-probe")"
[[ "$HTTP" == "200" ]] || fail "org auth-probe → want 200 got $HTTP"
pass "proxy org-scoped auth-probe → 200"

ORG_B="00000000-0000-0000-0000-0000000000b1"
HTTP="$(http_code -H "Authorization: Bearer $DEV_TOKEN" \
  -H "X-IBEX-Agent-ID: $AGENT_A" \
  "$PROXY_ADDR/v1/orgs/$ORG_B/auth-probe")"
[[ "$HTTP" == "403" ]] || fail "wrong-org path → want 403 got $HTTP"
pass "proxy wrong-org path auth-probe → 403"

echo ""
echo "=== Wave 2b compose-dev E2E: ALL PASSED ==="
