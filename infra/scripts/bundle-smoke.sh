#!/usr/bin/env bash
# Bundle smoke test for the memory-context supported profile.
#
# Proves: migrations are clean at the highest local version; AuthService,
# embedder, and memory are healthy; a memory can be created and found by
# search; duplicate content returns 409; a missing token returns 401; and an
# agent from another organization is not readable.
#
# Logs identifiers and status codes only. It never prints memory content.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/compose/bundles/memory-context.yml"
PROJECT="${BUNDLE_COMPOSE_PROJECT:-ibex-memory-context-smoke}"
BASE_URL="${BUNDLE_MEMORY_URL:-http://127.0.0.1:18005}"
PAT="${BUNDLE_DEV_PAT:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
AGENT_A="00000000-0000-0000-0000-000000000003"
ORG_B="00000000-0000-0000-0000-000000000010"
AGENT_B="00000000-0000-0000-0000-000000000011"
RESULT_FILE="${BUNDLE_SMOKE_RESULT:-$ROOT_DIR/bundle-smoke-result.json}"
KEEP="${BUNDLE_KEEP:-0}"
TMP_DIR="$(mktemp -d)"

fail() {
  echo "bundle-smoke: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

cleanup() {
  rm -rf "$TMP_DIR"
  if [[ "$KEEP" == "1" ]]; then
    echo "bundle-smoke: keeping stack ($PROJECT)"
    return
  fi
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}

compose() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

refuse_non_local() {
  if [[ "${IBEX_ENV:-}" == "production" ]]; then
    fail "refusing to run with IBEX_ENV=production"
  fi
  case "$BASE_URL" in
    http://127.0.0.1:* | http://localhost:*) ;;
    *) fail "BUNDLE_MEMORY_URL must be a loopback URL, got: $BASE_URL" ;;
  esac
}

wait_http() {
  local url="$1" label="$2" attempts=90
  for ((i = 0; i < attempts; i++)); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      pass "$label is healthy"
      return 0
    fi
    sleep 2
  done
  compose ps >&2 || true
  fail "timed out waiting for $label ($url)"
}

psql_scalar() {
  compose exec -T postgres psql -U ibex -d ibex -v ON_ERROR_STOP=1 -tAc "$1"
}

wait_for_seed() {
  local attempts=60
  for ((i = 0; i < attempts; i++)); do
    if [[ "$(psql_scalar "select count(*) from ibex_core.agents where id = '$AGENT_A'")" == "1" ]]; then
      pass "dev seed agent is present"
      return 0
    fi
    sleep 2
  done
  compose logs seed >&2 || true
  fail "dev seed did not create the bundle agent"
}

expected_migration_version() {
  local latest
  latest="$(find "$ROOT_DIR/infra/migrations/postgres" -name '*.up.sql' -printf '%f\n' |
    sed -E 's/^([0-9]+)_.*/\1/' |
    sort -n |
    tail -1)"
  echo $((10#$latest))
}

check_migrations() {
  local expected line
  expected="$(expected_migration_version)"
  line="$(compose run --rm --no-deps migrate version | tail -1)"
  if [[ "$line" != "version=$expected dirty=false" ]]; then
    fail "migration state mismatch: got '$line', want 'version=$expected dirty=false'"
  fi
  pass "migrations are clean at version $expected"
}

seed_second_tenant() {
  psql_scalar "
    BEGIN;
    SELECT set_config('app.is_service_account', 'true', true);
    INSERT INTO ibex_core.organizations (id, name, slug, tier, status)
    VALUES ('$ORG_B', 'Bundle Smoke Org B', 'bundle-smoke-org-b', 'free', 'active')
    ON CONFLICT (id) DO NOTHING;
    INSERT INTO ibex_core.agents (id, org_id, name, slug, status)
    VALUES ('$AGENT_B', '$ORG_B', 'Bundle Smoke Agent B', 'bundle-smoke-agent-b', 'active')
    ON CONFLICT (id) DO NOTHING;
    COMMIT;
  " >/dev/null
  pass "second-tenant agent seeded"
}

create_memory() {
  local status
  status="$(curl -sS -o "$TMP_DIR/create.json" -w '%{http_code}' \
    -X POST "$BASE_URL/v1/memories" \
    --oauth2-bearer "$PAT" \
    -H "Content-Type: application/json" \
    -H "X-Idempotency-Key: bundle-smoke-create-1" \
    -d "{\"agent_id\":\"$AGENT_A\",\"content\":\"The bundle smoke sentence is benign and retrievable.\",\"category\":\"factual\"}")"
  [[ "$status" == "201" ]] || fail "create returned $status"
  python3 - "$TMP_DIR/create.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
memory = data["data"]
if memory["status"] != "active":
    raise SystemExit(f"created memory is {memory['status']}, not active")
print(memory["id"])
PY
}

search_memory() {
  local memory_id="$1" status
  status="$(curl -sS -o "$TMP_DIR/search.json" -w '%{http_code}' \
    -X POST "$BASE_URL/v1/memories/search" \
    --oauth2-bearer "$PAT" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$AGENT_A\",\"query\":\"bundle smoke retrievable sentence\",\"min_similarity\":0,\"limit\":5}")"
  [[ "$status" == "200" ]] || fail "search returned $status"
  python3 - "$TMP_DIR/search.json" "$memory_id" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
ids = [item["memory"]["id"] for item in data["data"]["results"]]
if sys.argv[2] not in ids:
    raise SystemExit("search did not return the created memory")
PY
}

assert_duplicate() {
  local status
  status="$(curl -sS -o "$TMP_DIR/duplicate.json" -w '%{http_code}' \
    -X POST "$BASE_URL/v1/memories" \
    --oauth2-bearer "$PAT" \
    -H "Content-Type: application/json" \
    -H "X-Idempotency-Key: bundle-smoke-create-2" \
    -d "{\"agent_id\":\"$AGENT_A\",\"content\":\"The bundle smoke sentence is benign and retrievable.\",\"category\":\"factual\"}")"
  [[ "$status" == "409" ]] || fail "duplicate create returned $status"
  python3 - "$TMP_DIR/duplicate.json" <<'PY'
import json
import sys

body = json.load(open(sys.argv[1], encoding="utf-8"))
detail = body.get("detail") or body.get("error") or {}
if not isinstance(detail, dict) or detail.get("code") != "DUPLICATE_CONTENT":
    raise SystemExit(f"unexpected duplicate error: {body}")
PY
  pass "duplicate content returns 409 DUPLICATE_CONTENT"
}

assert_unauthenticated() {
  local status
  status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -X POST "$BASE_URL/v1/memories/search" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$AGENT_A\",\"query\":\"no token\",\"limit\":1}")"
  [[ "$status" == "401" ]] || fail "unauthenticated search returned $status"
  pass "missing token returns 401"
}

assert_cross_tenant_denied() {
  local status
  status="$(curl -sS -o "$TMP_DIR/cross-tenant.json" -w '%{http_code}' \
    -X POST "$BASE_URL/v1/memories/search" \
    --oauth2-bearer "$PAT" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$AGENT_B\",\"query\":\"cross tenant\",\"min_similarity\":0,\"limit\":1}")"
  [[ "$status" == "403" || "$status" == "404" ]] || fail "cross-tenant search returned $status, want 403 or 404"
  pass "another organization's agent is not readable ($status)"
}

write_result() {
  local commit="${GITHUB_SHA:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"
  python3 - "$RESULT_FILE" "$commit" <<'PY'
import json
import sys
from datetime import UTC, datetime

path, commit = sys.argv[1], sys.argv[2]
json.dump(
    {
        "bundle": "memory-context",
        "status": "passed",
        "commit": commit,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    },
    open(path, "w", encoding="utf-8"),
    indent=2,
    sort_keys=True,
)
PY
  echo "bundle-smoke: wrote $RESULT_FILE"
}

refuse_non_local
trap cleanup EXIT
compose down -v --remove-orphans >/dev/null 2>&1 || true
compose up -d --build

wait_http "$BASE_URL/health" "memory /health"
wait_http "$BASE_URL/ready" "memory /ready"
compose exec -T auth wget -qO- http://127.0.0.1:8081/health >/dev/null
pass "auth /health"
compose exec -T embedder python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8004/health')" >/dev/null
pass "embedder /health"
wait_for_seed
check_migrations
seed_second_tenant

memory_id="$(create_memory)"
pass "created memory $memory_id"
search_memory "$memory_id"
pass "search returned the created memory"
assert_duplicate
assert_unauthenticated
assert_cross_tenant_denied
write_result
pass "memory-context bundle smoke passed"
