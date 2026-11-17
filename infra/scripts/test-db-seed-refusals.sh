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
# `make db-seed`, so deleting one would have been silent. No database is
# contacted here — every case stops at the refusal, or (for the control case)
# at the connection attempt against a closed port in its own temporary DSN.
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

# run_seed runs db-seed.sh with a chosen environment and captures its output.
# POSTGRES_DSN is always set explicitly so the script never loads the dev
# .env.example: the test does not depend on a developer's working tree.
run_seed() {
  local out="$1"
  shift
  env -i PATH="$PATH" HOME="${HOME:-/tmp}" "$@" bash "$SEED" >"$out" 2>&1
}

# --- case 1: IBEX_ENV=production is refused --------------------------------

out="$(mktemp)"
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
rm -f "$out"
pass "IBEX_ENV=production is refused before any SQL runs"

# --- case 2: a non-local POSTGRES_DSN host is refused ----------------------

out="$(mktemp)"
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
rm -f "$out"
pass "a non-local POSTGRES_DSN host is refused before any SQL runs"

# --- case 3: an unparseable host fails closed ------------------------------

out="$(mktemp)"
if run_seed "$out" \
  IBEX_ENV=development \
  POSTGRES_DSN="postgres:///ibex?sslmode=disable"; then
  cat "$out" >&2
  fail "unparseable host: db-seed exited 0 instead of failing closed"
fi
grep -q 'cannot parse host from POSTGRES_DSN (fail closed)' "$out" \
  || fail "unparseable host: fail-closed message missing"
rm -f "$out"
pass "an unparseable host fails closed"

# --- case 4: the control case is not refused -------------------------------
#
# A local DSN on a closed port must get past both refusals and fail later, at
# the connection. Without this case every assertion above would also pass if
# db-seed refused everything.

out="$(mktemp)"
if run_seed "$out" \
  IBEX_ENV=development \
  POSTGRES_DSN="postgres://ibex:ibex@127.0.0.1:5999/ibex?sslmode=disable"; then
  cat "$out" >&2
  fail "control case: db-seed unexpectedly succeeded against a closed port"
fi
if grep -q 'refusing db-seed' "$out"; then
  cat "$out" >&2
  fail "control case: a local DSN was refused by a guard instead of reaching the connection"
fi
grep -q 'Seeding development database' "$out" \
  || fail "control case: the script never reached the seed step"
rm -f "$out"
pass "a local DSN passes both guards and fails only at the connection"

echo "db-seed refusal tests: PASS ($PASSED cases)"
