#!/usr/bin/env bash
# test-db-seed-refusals.sh — regression tests for db-seed.sh's two guards.
#
# db-seed.sh writes a development seed into a database. It is safe only because
# two checks refuse the run before psql is reached (P2-13):
#
#   1. IBEX_ENV=production is refused. The seed creates a known org, agent and a
#      fixed development PAT; running it against a production database installs a
#      credential that is published in the repository.
#   2. A POSTGRES_DSN host that is not local is refused, and an unparseable host
#      fails closed rather than guessing.
#
# Neither refusal had a test: the guards were reached only through a manual
# `make db-seed`, so deleting one would have been silent.
#
# Nothing here can contact a database. `psql` and `docker` are stubbed in a
# directory ahead of PATH: each stub records its call and exits non-zero. A
# regressed guard therefore reaches a stub, not a real localhost:5432, and the
# control case cannot run seed_dev.sql against whatever answers on
# 127.0.0.1:5999. Every refusal case asserts that no client was called at all;
# the control case asserts exactly one `psql` call, which is the seed step the
# guards are supposed to let through.
#
# Run directly: bash infra/scripts/test-db-seed-refusals.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SEED="$ROOT_DIR/infra/scripts/db-seed.sh"

PASSED=0
pass() {
  PASSED=$((PASSED + 1))
  echo "PASS: $*"
}
fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "$SEED" ]] || fail "db-seed.sh not found at $SEED"

WORK="$(mktemp -d)"
cleanup() {
  rm -rf "$WORK"
}
trap cleanup EXIT

STUB_BIN="$WORK/bin"
STUB_LOG="$WORK/client-calls.log"
mkdir -p "$STUB_BIN"
: >"$STUB_LOG"

# write_client_stub installs a psql or docker that records its argv and fails.
# The non-zero status makes a regressed guard fail the run the way a refusal
# does, so only the call log tells the two apart.
write_client_stub() {
  local target="$STUB_BIN/$1"
  cat >"$target" <<'STUB'
#!/usr/bin/env bash
printf '%s %s\n' "${0##*/}" "$*" >>"${CLIENT_STUB_LOG:?}"
exit 1
STUB
  chmod 0755 "$target"
}
write_client_stub psql
write_client_stub docker

# client_calls counts the calls one stub received since the last reset.
client_calls() {
  local count
  count="$(grep -c "^$1 " "$STUB_LOG" 2>/dev/null || true)"
  printf '%s' "${count:-0}"
}

# expect_no_client_calls asserts a refusal happened before any client was used.
expect_no_client_calls() {
  local name="$1" program count
  for program in psql docker; do
    count="$(client_calls "$program")"
    if [[ "$count" != "0" ]]; then
      cat "$STUB_LOG" >&2
      fail "$name: $program was called $count time(s) before the refusal"
    fi
  done
}

# run_seed runs db-seed.sh with a chosen environment and captures its output.
# POSTGRES_DSN is always set explicitly so the script never loads the dev
# .env.example: the test does not depend on a developer's working tree.
run_seed() {
  local out="$1"
  shift
  : >"$STUB_LOG"
  env -i PATH="$STUB_BIN:$PATH" HOME="${HOME:-/tmp}" \
    CLIENT_STUB_LOG="$STUB_LOG" "$@" bash "$SEED" >"$out" 2>&1
}

# --- case 1: IBEX_ENV=production is refused --------------------------------

out="$WORK/production.out"
if run_seed "$out" \
  IBEX_ENV=production \
  POSTGRES_DSN="postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"; then
  cat "$out" >&2
  fail "IBEX_ENV=production: db-seed exited 0 instead of refusing"
fi
grep -q 'refusing db-seed: IBEX_ENV=production' "$out" \
  || fail "IBEX_ENV=production: refusal message missing"
if grep -q 'Seeding development database' "$out"; then
  fail "IBEX_ENV=production: the script reached the seed step before refusing"
fi
expect_no_client_calls "IBEX_ENV=production"
pass "IBEX_ENV=production is refused before any client is called"

# --- case 2: a non-local POSTGRES_DSN host is refused ----------------------

out="$WORK/non-local.out"
if run_seed "$out" \
  IBEX_ENV=development \
  POSTGRES_DSN="postgres://ibex:ibex@db.prod.example.com:5432/ibex?sslmode=disable"; then
  cat "$out" >&2
  fail "non-local host: db-seed exited 0 instead of refusing"
fi
grep -q "refusing db-seed: POSTGRES_DSN host 'db.prod.example.com' does not look local" "$out" \
  || fail "non-local host: refusal message missing"
if grep -q 'Seeding development database' "$out"; then
  fail "non-local host: the script reached the seed step before refusing"
fi
expect_no_client_calls "non-local host"
pass "a non-local POSTGRES_DSN host is refused before any client is called"

# --- case 3: an unparseable host fails closed ------------------------------

out="$WORK/unparseable.out"
if run_seed "$out" \
  IBEX_ENV=development \
  POSTGRES_DSN="postgres:///ibex?sslmode=disable"; then
  cat "$out" >&2
  fail "unparseable host: db-seed exited 0 instead of failing closed"
fi
grep -q 'cannot parse host from POSTGRES_DSN (fail closed)' "$out" \
  || fail "unparseable host: fail-closed message missing"
expect_no_client_calls "unparseable host"
pass "an unparseable host fails closed before any client is called"

# --- case 4: the control case is not refused -------------------------------
#
# A local DSN must get past both refusals and reach the seed step. Without this
# case every assertion above would also pass if db-seed refused everything. The
# stubbed psql is the only client it may reach, and exactly once: one seed run.

out="$WORK/control.out"
if run_seed "$out" \
  IBEX_ENV=development \
  POSTGRES_DSN="postgres://ibex:ibex@127.0.0.1:5999/ibex?sslmode=disable"; then
  cat "$out" >&2
  fail "control case: db-seed unexpectedly succeeded with a stubbed psql"
fi
if grep -q 'refusing db-seed' "$out"; then
  cat "$out" >&2
  fail "control case: a local DSN was refused by a guard instead of reaching the seed step"
fi
grep -q 'Seeding development database' "$out" \
  || fail "control case: the script never reached the seed step"
[[ "$(client_calls psql)" == "1" ]] \
  || fail "control case: psql was called $(client_calls psql) time(s), expected exactly 1"
[[ "$(client_calls docker)" == "0" ]] \
  || fail "control case: docker was called although psql was on PATH"
pass "a local DSN passes both guards and runs the seed through exactly one psql call"

echo "db-seed refusal tests: PASS ($PASSED cases)"
