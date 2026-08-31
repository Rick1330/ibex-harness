#!/usr/bin/env bash
# Phase 3 memory HTTP lifecycle e2e (m3.E.2): PII, dedup, near-dup escalation,
# sequential auto-supersede, composite search ranking, FK-cascade teardown,
# Redis stale-cache visibility (org GDPR deferred #641).
#
# Modes:
#   IBEX_E2E_PHASE3_MANAGE=1 (default) — start/stop auth + stub TEI + embedder + memory
#   IBEX_E2E_PHASE3_MANAGE=0 — use already-running services on default ports
#
# Prerequisites (manage mode): make compose-test-up && make db-migrate && make db-seed
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

AUTH_HTTP="${IBEX_AUTH_HTTP:-http://127.0.0.1:18081}"
AUTH_GRPC_PORT="${IBEX_GRPC_PORT:-19091}"
STUB_TEI_PORT="${IBEX_E2E_STUB_TEI_PORT:-18083}"
EMBEDDER_ADDR="${IBEX_EMBEDDER_ADDR:-http://127.0.0.1:18004}"
MEMORY_ADDR="${IBEX_MEMORY_ADDR:-http://127.0.0.1:8005}"
DEV_TOKEN="${IBEX_DEV_TOKEN:-ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY}"
DEV_ORG="${IBEX_DEV_ORG_ID:-00000000-0000-0000-0000-000000000001}"
DEV_AGENT="${IBEX_DEV_AGENT_ID:-00000000-0000-0000-0000-000000000003}"
EMBED_TOKEN="${IBEX_EMBEDDING_API_TOKEN:-dev-embedder-metrics-token}"
MANAGE="${IBEX_E2E_PHASE3_MANAGE:-1}"
LOG_DIR="${IBEX_E2E_PHASE3_LOG_DIR:-/tmp/ibex-e2e-phase3-memory}"
SEED_PY="$ROOT_DIR/infra/scripts/verify_phase3_memory_e2e_seed.py"
STUB_TEI_PY="$ROOT_DIR/infra/scripts/phase3_e2e_stub_tei.py"
MEMORY_DIR="$ROOT_DIR/services/memory"
EMBEDDER_DIR="$ROOT_DIR/services/embedder"
PORT_FROM_URL_SED='s#.*:([0-9]+).*#\1#'
DOCKER_PS_FORMAT='{{.Names}}'
PSQL_PING='SELECT 1'
SERVICE_MEMORY='memory'

# Calibrated against gpu-profile StubBackend (1024-d) via phase3_e2e_stub_tei.
# Hash-based stub cannot reach production 0.92; e2e uses lowered threshold (see below).
# Strings must be Presidio-clean (no quarantine on write); digit-dash patterns false-positive.
NEAR_DUP_A='ibex phase three memory lifecycle near duplicate neutral marker token slot 605'
NEAR_DUP_B='ibex phase three memory lifecycle near duplicate neutral marker token slot 606'
NEAR_DUP_MIN_SIM='0.08'
PII_CONTENT='My SSN is 856-45-6789 on file'
# ADR-0056 sequential supersede pair (stub-calibrated adjacent slots; isolated from 605/606).
SUPERSEDE_OLD='ibex phase three memory lifecycle near duplicate neutral marker token slot 621'
SUPERSEDE_NEW='ibex phase three memory lifecycle near duplicate neutral marker token slot 622'
# Redis delete-path invalidation deferred — see ADR-0059 / tracking issue in step 5 comment.
REDIS_INVALIDATION_ISSUE='647'

PIDS=()
BODY_FILE=""
LAST_HTTP_CODE=""
CODE=""
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

sanitized_error_code() {
  if [[ -n "${BODY_FILE:-}" && -f "$BODY_FILE" ]]; then
    jq -r '.detail.code // .error.code // .data.status // "unknown"' "$BODY_FILE" 2>/dev/null \
      || echo "unknown"
  else
    echo "unknown"
  fi
}

expect_http() {
  local got="$1"
  local want="$2"
  local ok_msg="$3"
  local fail_msg="$4"
  if [[ "$got" == "$want" ]]; then
    pass "$ok_msg"
  else
    echo "http_status=${got} expected=${want} error_code=$(sanitized_error_code)" >&2
    fail "$fail_msg"
  fi
}

prom_counter_total() {
  local name="$1"
  curl -fsS --connect-timeout 2 --max-time 10 "$MEMORY_ADDR/metrics" \
    | awk -v n="$name" '$1 == n { print $2; exit }'
}

cleanup() {
  if [[ -n "${BODY_FILE:-}" && -f "$BODY_FILE" ]]; then
    rm -f "$BODY_FILE"
  fi
  if [[ "$MANAGE" != "1" ]]; then
    return 0
  fi
  local pid
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

wait_http() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-120}"
  for _ in $(seq 1 "$max_attempts"); do
    if curl -fsS --connect-timeout 1 --max-time 3 "$url" >/dev/null 2>&1; then
      pass "$name ready ($url)"
      return 0
    fi
    sleep 0.5
  done
  fail "$name not ready: $url"
}

http_code() {
  if [[ -z "${BODY_FILE:-}" ]]; then
    BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/ibex-e2e-p3-body.XXXXXX")"
  fi
  LAST_HTTP_CODE="$(curl -sS --connect-timeout 2 --max-time 30 -o "$BODY_FILE" -w "%{http_code}" "$@" || true)"
}

do_http() {
  http_code "$@"
  CODE="$LAST_HTTP_CODE"
}

normalize_psql_dsn() {
  local dsn="$1"
  dsn="${dsn//postgresql+asyncpg:/postgres:}"
  dsn="${dsn//postgresql:/postgres:}"
  echo "$dsn"
}

run_psql() {
  local dsn
  dsn="$(normalize_psql_dsn "${POSTGRES_DSN}")"
  if command -v psql >/dev/null 2>&1; then
    psql "$dsn" -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx ibex-test-postgres; then
    docker exec ibex-test-postgres psql -U ibex -d ibex_test -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx test-postgres-1; then
    docker exec test-postgres-1 psql -U ibex -d ibex_test -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx ibex-dev-postgres; then
    docker exec ibex-dev-postgres psql -U ibex -d ibex -v ON_ERROR_STOP=1 "$@"
    return 0
  fi
  fail "psql not available for cascade DELETE"
}

docker_postgres_ping() {
  local container="$1"
  local label="$2"
  if docker ps --format "$DOCKER_PS_FORMAT" 2>/dev/null | grep -qx "$container" \
    && docker exec "$container" psql -U ibex -d ibex_test -v ON_ERROR_STOP=1 -c "$PSQL_PING" >/dev/null 2>&1; then
    pass "postgres reachable ($label)"
    return 0
  fi
  return 1
}

postgres_preflight() {
  local dsn
  dsn="$(normalize_psql_dsn "${POSTGRES_DSN}")"
  if command -v psql >/dev/null 2>&1; then
    if psql "$dsn" -v ON_ERROR_STOP=1 -c "$PSQL_PING" >/dev/null 2>&1; then
      pass "postgres reachable ($dsn)"
      return 0
    fi
    fail "Postgres not reachable at POSTGRES_DSN (check host/port and migrations)"
  fi
  if docker_postgres_ping ibex-test-postgres ibex-test-postgres; then
    return 0
  fi
  if docker_postgres_ping test-postgres-1 test-postgres-1; then
    return 0
  fi
  if docker_postgres_ping ibex-dev-postgres ibex-dev-postgres; then
    return 0
  fi
  fail "Postgres not reachable at POSTGRES_DSN (make compose-test-up && make db-migrate)"
}

memory_seed() {
  cd "$MEMORY_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python "$SEED_PY" "$@"
}

verify_near_dup_pii_clean() {
  cd "$MEMORY_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python - <<PY
import asyncio, sys
from app.config import Settings
from app.pii.service import PiiService

a = ${NEAR_DUP_A@Q}
b = ${NEAR_DUP_B@Q}

async def main():
    pii = PiiService(Settings(database_url="postgresql+asyncpg://x"))
    await pii.ensure_ready()
    for label, text in (("A", a), ("B", b)):
        result = await pii.process_async(text)
        if result.pii_detected:
            print(f"near-dup PII guard: {label} flagged", file=sys.stderr)
            sys.exit(1)

asyncio.run(main())
PY
}

verify_near_dup_calibration() {
  cd "$EMBEDDER_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python - <<PY
import asyncio, json, os, sys
import httpx

a = ${NEAR_DUP_A@Q}
b = ${NEAR_DUP_B@Q}
min_sim = float(${NEAR_DUP_MIN_SIM@Q})
url = os.environ["EMBEDDER_ADDR"].rstrip("/") + "/v1/embed"
token = os.environ["EMBED_TOKEN"]
org = os.environ["DEV_ORG"]

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"texts": [a, b], "org_id": org},
        )
    if r.status_code != 200:
        print(f"near-dup calibration: embedder returned {r.status_code}", file=sys.stderr)
        sys.exit(1)
    body = r.json()
    va, vb = body["vectors"][0], body["vectors"][1]
    sim = sum(x * y for x, y in zip(va, vb, strict=True))
    if sim <= min_sim:
        print(
            f"near-dup calibration failed: cosine={sim:.6f} threshold>{min_sim}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps({"similarity": sim, "threshold": min_sim}))

asyncio.run(main())
PY
}

verify_supersede_calibration() {
  cd "$EMBEDDER_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python - <<PY
import asyncio, json, os, sys
import httpx

old = ${SUPERSEDE_OLD@Q}
new = ${SUPERSEDE_NEW@Q}
min_sim = float(${NEAR_DUP_MIN_SIM@Q})
url = os.environ["EMBEDDER_ADDR"].rstrip("/") + "/v1/embed"
token = os.environ["EMBED_TOKEN"]
org = os.environ["DEV_ORG"]

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"texts": [old, new], "org_id": org},
        )
    if r.status_code != 200:
        print(f"supersede calibration: embedder returned {r.status_code}", file=sys.stderr)
        sys.exit(1)
    body = r.json()
    va, vb = body["vectors"][0], body["vectors"][1]
    sim = sum(x * y for x, y in zip(va, vb, strict=True))
    if sim <= min_sim:
        print(
            f"supersede calibration failed: cosine={sim:.6f} threshold>{min_sim}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps({"similarity": sim, "threshold": min_sim}))

asyncio.run(main())
PY
}

verify_supersede_subjects() {
  cd "$MEMORY_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python - <<PY
import sys
from app.config import Settings
from app.conflict.subjects import extract_subject_key, subjects_match

old = ${SUPERSEDE_OLD@Q}
new = ${SUPERSEDE_NEW@Q}
model = Settings(database_url="postgresql+asyncpg://x").pii_spacy_model
left = extract_subject_key(old, model_name=model)
right = extract_subject_key(new, model_name=model)
if not subjects_match(left, right):
    print(
        f"supersede subject guard: no match ({left!r} vs {right!r})",
        file=sys.stderr,
    )
    sys.exit(1)
PY
}

start_stack() {
  mkdir -p "$LOG_DIR"
  export IBEX_ENV=development
  export POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable}"
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/0}"
  export IBEX_AUTH_VALIDATE_TIMEOUT="${IBEX_AUTH_VALIDATE_TIMEOUT:-2s}"

  local auth_http_port embedder_port memory_port
  auth_http_port="$(echo "$AUTH_HTTP" | sed -E "$PORT_FROM_URL_SED")"
  embedder_port="$(echo "$EMBEDDER_ADDR" | sed -E "$PORT_FROM_URL_SED")"
  memory_port="$(echo "$MEMORY_ADDR" | sed -E "$PORT_FROM_URL_SED")"

  echo "e2e-phase3-memory: starting auth on :${auth_http_port}/:${AUTH_GRPC_PORT}..."
  IBEX_PORT="$auth_http_port" IBEX_GRPC_PORT="$AUTH_GRPC_PORT" OTEL_SERVICE_NAME=ibex-auth \
    go run ./services/auth/cmd/auth >"$LOG_DIR/auth.log" 2>&1 &
  PIDS+=("$!")
  wait_http "auth" "$AUTH_HTTP/health"

  echo "e2e-phase3-memory: starting stub TEI (1024-d) on :${STUB_TEI_PORT}..."
  export PYTHONPATH="$EMBEDDER_DIR${PYTHONPATH:+:$PYTHONPATH}"
  (
    cd "$EMBEDDER_DIR"
    if [[ ! -d .venv ]]; then
      uv sync --frozen --no-build >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec python "$STUB_TEI_PY" --host 127.0.0.1 --port "$STUB_TEI_PORT"
  ) >"$LOG_DIR/stub-tei.log" 2>&1 &
  PIDS+=("$!")
  wait_http "stub-tei" "http://127.0.0.1:${STUB_TEI_PORT}/health"

  echo "e2e-phase3-memory: starting embedder (gpu→stub TEI) on :${embedder_port}..."
  export IBEX_EMBEDDING_PROFILE=gpu
  export IBEX_EMBEDDING_TEI_BASE_URL="http://127.0.0.1:${STUB_TEI_PORT}"
  export IBEX_EMBEDDING_TEI_ALLOW_INSECURE=true
  export IBEX_EMBEDDING_DIM=1024
  export IBEX_EMBEDDING_MODEL=BAAI/bge-m3
  export IBEX_EMBEDDING_API_TOKEN="$EMBED_TOKEN"
  export IBEX_EMBEDDING_CACHE_ENABLED=false
  (
    cd "$EMBEDDER_DIR"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec uvicorn app.main:app --host 127.0.0.1 --port "$embedder_port"
  ) >"$LOG_DIR/embedder.log" 2>&1 &
  PIDS+=("$!")
  wait_http "embedder" "$EMBEDDER_ADDR/health"

  echo "e2e-phase3-memory: starting memory on :${memory_port}..."
  export IBEX_MEMORY_DATABASE_URL="${POSTGRES_DSN}"
  export IBEX_MEMORY_REDIS_URL="${REDIS_URL}"
  export IBEX_AUTH_GRPC_ADDR="127.0.0.1:${AUTH_GRPC_PORT}"
  export IBEX_MEMORY_AUTH_TIMEOUT_MS="${IBEX_MEMORY_AUTH_TIMEOUT_MS:-2000}"
  export IBEX_MEMORY_EMBEDDING_BASE_URL="$EMBEDDER_ADDR"
  export IBEX_MEMORY_NEAR_DUPLICATE_SIM_THRESHOLD="$NEAR_DUP_MIN_SIM"
  (
    cd "$MEMORY_DIR"
    if [[ ! -d .venv ]]; then
      bash "$ROOT_DIR/infra/scripts/memory-uv-sync.sh" >/dev/null
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec uvicorn app.main:app --host 127.0.0.1 --port "$memory_port"
  ) >"$LOG_DIR/memory.log" 2>&1 &
  PIDS+=("$!")
  wait_http "$SERVICE_MEMORY" "$MEMORY_ADDR/health" 180
  wait_http "$SERVICE_MEMORY" "$MEMORY_ADDR/ready" 180
}

echo "=== Phase 3 memory HTTP lifecycle e2e (m3.E.2) ==="
echo "  manage=$MANAGE logs=$LOG_DIR"

if [[ "$MANAGE" == "1" ]]; then
  export POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable}"
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/0}"
  postgres_preflight
  bash "$ROOT_DIR/infra/scripts/db-seed.sh" >/dev/null
  bash "$ROOT_DIR/infra/scripts/memory-uv-sync.sh" >/dev/null
  start_stack
else
  wait_http "auth" "$AUTH_HTTP/health"
  wait_http "embedder" "$EMBEDDER_ADDR/health"
  wait_http "$SERVICE_MEMORY" "$MEMORY_ADDR/health"
  wait_http "$SERVICE_MEMORY" "$MEMORY_ADDR/ready"
fi

export EMBEDDER_ADDR DEV_ORG EMBED_TOKEN
export POSTGRES_DSN="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable}"
export IBEX_MEMORY_DATABASE_URL="$POSTGRES_DSN"
memory_seed fixture-cleanup --org-id "$DEV_ORG" --agent-id "$DEV_AGENT"
pass "fixture cleanup complete"

verify_near_dup_pii_clean
pass "near-dup pair PII-clean"

CALIB="$(verify_near_dup_calibration)"
pass "near-dup pair calibrated ($CALIB)"

AUTH_HEADER=(-H "Authorization: Bearer $DEV_TOKEN" -H "Content-Type: application/json")

# --- Step 4: composite search ranking (SQL seed + HTTP search) — before steps 1–3 ---
# Isolated ranking pair on a clean org (matches integration test_composite_ranking_http).
RANK_JSON="$(memory_seed ranking-seed --org-id "$DEV_ORG" --agent-id "$DEV_AGENT")"
FACTUAL_ID="$(echo "$RANK_JSON" | jq -r '.factual_id')"
SEARCH_PAYLOAD="$(jq -nc --arg agent "$DEV_AGENT" \
  '{agent_id:$agent, query:"dark mode preference", limit:5, min_similarity:0.0}')"
do_http -X POST "$MEMORY_ADDR/v1/memories/search" "${AUTH_HEADER[@]}" -d "$SEARCH_PAYLOAD"
expect_http "$CODE" "200" "step 4: POST /v1/memories/search" "step 4: expected 200 got $CODE"
TOP_CATEGORY="$(jq -r '.data.results[0].memory.category // empty' "$BODY_FILE")"
TOP_ID="$(jq -r '.data.results[0].memory.id // empty' "$BODY_FILE")"
[[ "$TOP_CATEGORY" == "factual" ]] || fail "step 4: top result category must be factual"
[[ "$TOP_ID" == "$FACTUAL_ID" ]] || fail "step 4: top result id must be factual seed"
pass "step 4: old factual outranks fresh episodic"

# --- Step 1: PII redaction on write ---
STEP1_PAYLOAD="$(jq -nc --arg agent "$DEV_AGENT" --arg content "$PII_CONTENT" \
  '{agent_id:$agent, content:$content}')"
do_http -X POST "$MEMORY_ADDR/v1/memories" "${AUTH_HEADER[@]}" -d "$STEP1_PAYLOAD"
expect_http "$CODE" "201" "step 1: POST /v1/memories (PII)" "step 1: expected 201 got $CODE"
PII_MEMORY_ID="$(jq -r '.data.id' "$BODY_FILE")"
PII_DETECTED="$(jq -r '.data.pii_detected' "$BODY_FILE")"
PII_CONTENT_OUT="$(jq -r '.data.content' "$BODY_FILE")"
[[ "$PII_DETECTED" == "true" ]] || fail "step 1: pii_detected must be true"
[[ "$PII_CONTENT_OUT" == *"[US_SSN]"* ]] || fail "step 1: content missing [US_SSN] placeholder"
[[ "$PII_CONTENT_OUT" != *"856-45-6789"* ]] || fail "step 1: raw SSN digits still present"
pass "step 1: PII redacted in data.content"

# --- Step 2: exact dedup 409 ---
do_http -X POST "$MEMORY_ADDR/v1/memories" "${AUTH_HEADER[@]}" -d "$STEP1_PAYLOAD"
expect_http "$CODE" "409" "step 2: duplicate content 409" "step 2: expected 409 got $CODE"
DUP_CODE="$(jq -r '.detail.code // .error.code // empty' "$BODY_FILE")"
EXISTING_ID="$(jq -r '.detail.existing_memory_id // empty' "$BODY_FILE")"
[[ "$DUP_CODE" == "DUPLICATE_CONTENT" ]] || fail "step 2: expected DUPLICATE_CONTENT got ${DUP_CODE:-<none>}"
[[ "$EXISTING_ID" == "$PII_MEMORY_ID" ]] || fail "step 2: existing_memory_id mismatch"
pass "step 2: exact dedup returns existing id"

# --- Step 3c: sequential auto-supersede (ADR-0056) — before near-dup escalation ---
# Memory A is SQL-seeded with closed [valid_from, valid_until): POST /v1/memories has no
# valid_from field today. Memory B is the HTTP write under test. Runs before step 3 so
# overlapping-interval near-dup candidates from 605/606 do not interfere.
verify_supersede_subjects
pass "step 3c: supersede pair subjects match"
verify_supersede_calibration >/dev/null
pass "step 3c: supersede pair calibrated for near-dup gate"
LLM_BEFORE_3C="$(prom_counter_total ibex_memory_conflict_llm_calls_total)"
[[ -n "$LLM_BEFORE_3C" ]] || fail "step 3c: could not read ibex_memory_conflict_llm_calls_total"
SUPERSEDE_JSON="$(memory_seed supersede-seed --org-id "$DEV_ORG" --agent-id "$DEV_AGENT" \
  --old-content "$SUPERSEDE_OLD")"
SUPERSEDE_OLD_ID="$(echo "$SUPERSEDE_JSON" | jq -r '.old_id')"
SUPERSEDE_PAYLOAD="$(jq -nc --arg agent "$DEV_AGENT" --arg content "$SUPERSEDE_NEW" \
  '{agent_id:$agent, content:$content}')"
do_http -X POST "$MEMORY_ADDR/v1/memories" "${AUTH_HEADER[@]}" -d "$SUPERSEDE_PAYLOAD"
expect_http "$CODE" "201" "step 3c: POST superseding memory B" "step 3c: expected 201 got $CODE"
SUPERSEDE_NEW_ID="$(jq -r '.data.id' "$BODY_FILE")"
memory_seed supersede-check --org-id "$DEV_ORG" --old-id "$SUPERSEDE_OLD_ID" \
  --new-id "$SUPERSEDE_NEW_ID"
LLM_AFTER_3C="$(prom_counter_total ibex_memory_conflict_llm_calls_total)"
[[ "$LLM_BEFORE_3C" == "$LLM_AFTER_3C" ]] \
  || fail "step 3c: ibex_memory_conflict_llm_calls_total changed ${LLM_BEFORE_3C} -> ${LLM_AFTER_3C}"
pass "step 3c: sequential auto-supersede (zero LLM calls for pair)"

# --- Step 3: near-dup conflict escalation ---
NEAR_A_PAYLOAD="$(jq -nc --arg agent "$DEV_AGENT" --arg content "$NEAR_DUP_A" \
  '{agent_id:$agent, content:$content}')"
do_http -X POST "$MEMORY_ADDR/v1/memories" "${AUTH_HEADER[@]}" -d "$NEAR_A_PAYLOAD"
expect_http "$CODE" "201" "step 3a: near-dup seed memory A" "step 3a: expected 201 got $CODE"
NEAR_A_ID="$(jq -r '.data.id' "$BODY_FILE")"

NEAR_B_PAYLOAD="$(jq -nc --arg agent "$DEV_AGENT" --arg content "$NEAR_DUP_B" \
  '{agent_id:$agent, content:$content}')"
do_http -X POST "$MEMORY_ADDR/v1/memories" "${AUTH_HEADER[@]}" -d "$NEAR_B_PAYLOAD"
expect_http "$CODE" "201" "step 3b: near-dup memory B" "step 3b: expected 201 got $CODE"
NEAR_B_ID="$(jq -r '.data.id' "$BODY_FILE")"
SIMILAR="$(jq -r --arg aid "$NEAR_A_ID" '.meta.deduplication.similar_memories | index($aid) != null' "$BODY_FILE")"
[[ "$SIMILAR" == "true" ]] || fail "step 3: similar_memories must include memory A"
export POSTGRES_DSN="${POSTGRES_DSN}"
export IBEX_MEMORY_DATABASE_URL="$POSTGRES_DSN"
memory_seed escalation-check --org-id "$DEV_ORG" --new-id "$NEAR_B_ID" --candidate-id "$NEAR_A_ID"
pass "step 3: pending memory_conflict_escalations row"

# --- Step 5: skip org GDPR (#641) + FK cascade DELETE + Redis stale-cache visibility ---
echo "SKIP: org-scope GDPR cascade + MinIO purge deferred to Phase 4.A.2 (#641)"
memory_seed cascade-setup --memory-id "$PII_MEMORY_ID" --org-id "$DEV_ORG" --agent-id "$DEV_AGENT"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380/0}"
memory_seed redis-cache-check --org-id "$DEV_ORG" --agent-id "$DEV_AGENT" \
  --memory-id "$PII_MEMORY_ID" --phase before-delete
pass "step 5: Redis object cache + hot ZSET populated after HTTP create"
run_psql <<SQL
BEGIN;
SELECT set_config('app.is_service_account', 'true', true);
SELECT set_config('app.current_org_id', '${DEV_ORG}', true);
DELETE FROM ibex_core.memories WHERE id = '${PII_MEMORY_ID}' AND org_id = '${DEV_ORG}';
COMMIT;
SQL
memory_seed cascade-check --memory-id "$PII_MEMORY_ID" --org-id "$DEV_ORG"
# MemoryHotCacheReader has no HTTP route; exercise hydrate read path via seed helper.
memory_seed hot-cache-read-check --org-id "$DEV_ORG" --agent-id "$DEV_AGENT" \
  --memory-id "$PII_MEMORY_ID" --expect-absent
pass "step 5: MemoryHotCacheReader omits deleted memory (hydrate filter)"
# Explicit ZREM / object-cache DEL on delete is deferred (ADR-0059). Stale entries are safe:
# MemoryHotCacheReader hydrates from Postgres and drops non-active rows — stale cache cannot
# leak deleted content, only omit results. Tracked: https://github.com/Rick1330/ibex-harness/issues/${REDIS_INVALIDATION_ISSUE}
memory_seed redis-cache-check --org-id "$DEV_ORG" --agent-id "$DEV_AGENT" \
  --memory-id "$PII_MEMORY_ID" --phase after-delete
pass "step 5: Redis stale cache after SQL DELETE (known gap #${REDIS_INVALIDATION_ISSUE})"
pass "step 5: FK cascade teardown (SQL DELETE, not HTTP)"

echo "=== Phase 3 memory e2e complete ==="
