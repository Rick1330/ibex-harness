#!/usr/bin/env bash
# Capability-login helpers for the shell harnesses.
#
# The v1 profile connects the application services on capability logins
# (`ibex_runtime` for memory/proxy/api, `ibex_worker` for the worker,
# `ibex_auth` for AuthService) and each binary asserts its connection login at
# startup. A wrong *password* fails loudly when the pool connects; a wrong
# *login* starts silently and re-enables the RLS bypass the tenancy guarantee
# rests on, because the migration owner `ibex` is a superuser and
# `FORCE ROW LEVEL SECURITY` does not cover superusers. The harnesses therefore
# give themselves two identities:
#
#   * the **app under test** connects on a capability login, so the startup
#     assertion passes and RLS is exercised for real;
#   * the **test** seeds and asserts as the owner, so fixtures are not blocked by
#     RLS and destructive helpers such as `TRUNCATE` stay possible.
#
# This is the shell twin of `infra/testing/pgcapability.py`; the secrets below
# are the same values as `infra/testing/pgcapability.py` and
# `infra/testing/testcreds/creds.go`. Roles and their verifiers are
# cluster-global, so every harness that provisions a cluster must use these exact
# values or it invalidates the connections another suite is already using. They
# are fixed on purpose and are not overridable.
#
# Usage (source it, do not execute it):
#   # shellcheck source=lib/pgcapability.sh
#   source "$ROOT/infra/scripts/lib/pgcapability.sh"

# Repository root, resolved from this file so a sourcing script need not pass it.
IBEX_PGCAPABILITY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

IBEX_RUNTIME_LOGIN='ibex_runtime'
IBEX_WORKER_LOGIN='ibex_worker'
IBEX_AUTH_LOGIN='ibex_auth'
IBEX_BOOTSTRAP_LOGIN='ibex_bootstrap'

# capability_password prints the fixed verifier for a capability login.
capability_password() {
  local login="$1"
  case "$login" in
    "$IBEX_RUNTIME_LOGIN") printf '%s' 'capability-test-only-runtime' ;;
    "$IBEX_WORKER_LOGIN") printf '%s' 'capability-test-only-worker' ;;
    "$IBEX_AUTH_LOGIN") printf '%s' 'capability-test-only-auth' ;;
    "$IBEX_BOOTSTRAP_LOGIN") printf '%s' 'capability-test-only-bootstrap' ;;
    *)
      printf 'capability_password: unknown capability login %s\n' "$login" >&2
      return 1
      ;;
  esac
}

# _urlencode percent-encodes one DSN userinfo component. Python's urllib is the
# library; hand-rolled escaping misses characters such as '%', '@', ':' and '/',
# and a raw password with any of them breaks the DSN.
_urlencode() {
  python3 -c 'import sys, urllib.parse; sys.stdout.write(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

# capability_dsn prints `owner_dsn` with the userinfo replaced by a capability
# login. The scheme, host, port, database, and query string are preserved, so a
# `postgresql+asyncpg://` URL stays async and `sslmode` survives. The login and
# password are percent-encoded, so a verifier containing '%', '@', ':' or '/'
# still yields a valid DSN. The optional third argument overrides the verifier
# and exists for the encoding test; production callers pass only the login.
capability_dsn() {
  local owner_dsn="$1"
  local login="$2"
  # nosemgrep: codacy.bash.security.hard-coded-password -- defaulted local, not a literal credential: assigned from capability_password on the next line; the ${3:-} form is an optional override used only by the encoding test.
  local password="${3:-}"
  local scheme rest authority tail hostport
  if [[ -z "$password" ]]; then
    # nosemgrep: codacy.bash.security.hard-coded-password - fixed test-only verifier for an ephemeral CI database; capability_password is the single source and no production credential is assigned here.
    password="$(capability_password "$login")" || return 1
  fi
  if [[ "$owner_dsn" != *'://'* ]]; then
    printf 'capability_dsn: %s is not a URL DSN\n' "$owner_dsn" >&2
    return 1
  fi
  scheme="${owner_dsn%%://*}"
  rest="${owner_dsn#*://}"
  if [[ "$rest" == */* ]]; then
    authority="${rest%%/*}"
    tail="/${rest#*/}"
  else
    authority="$rest"
    tail=""
  fi
  hostport="${authority##*@}"
  if [[ -z "$hostport" ]]; then
    printf 'capability_dsn: %s carries no host\n' "$owner_dsn" >&2
    return 1
  fi
  printf '%s://%s:%s@%s%s' \
    "$scheme" "$(_urlencode "$login")" "$(_urlencode "$password")" "$hostport" "$tail"
}

# libpq_dsn strips a SQLAlchemy driver suffix so the Go migration CLI (lib/pq)
# can open the same database. Mirrors `libpq_dsn` in pgcapability.py.
libpq_dsn() {
  local dsn="$1"
  case "$dsn" in
    postgresql+asyncpg://*) printf 'postgresql://%s' "${dsn#postgresql+asyncpg://}" ;;
    postgres+asyncpg://*) printf 'postgres://%s' "${dsn#postgres+asyncpg://}" ;;
    *) printf '%s' "$dsn" ;;
  esac
}

# provision_capability_logins sets each capability role's SCRAM verifier and
# lifts its CONNECTION LIMIT 0 with `migrate provision`.
#
# Migration 000064 creates the roles with no password and no connection slots, so
# a capability login is refused before the service's own assertion is even
# reached. Provisioning needs the migrations applied (the roles must exist) and is
# idempotent, so a harness may call it once per run even when another suite
# already provisioned the cluster. The owner DSN is passed explicitly and both
# names the migration CLI reads are set, so an inherited POSTGRES_MIGRATE_DSN
# cannot redirect provisioning away from the database under test.
provision_capability_logins() {
  local owner_dsn="$1"
  local target
  if ! command -v go >/dev/null 2>&1; then
    printf 'provision_capability_logins: go is required to run migrate provision\n' >&2
    return 1
  fi
  target="$(libpq_dsn "$owner_dsn")"
  printf 'provisioning capability logins (%s, %s, %s, %s)...\n' \
    "$IBEX_AUTH_LOGIN" "$IBEX_RUNTIME_LOGIN" "$IBEX_WORKER_LOGIN" "$IBEX_BOOTSTRAP_LOGIN" >&2
  (
    cd "$IBEX_PGCAPABILITY_ROOT" || return 1
    POSTGRES_DSN="$target" \
      POSTGRES_MIGRATE_DSN="$target" \
      IBEX_RUNTIME_DB_PASSWORD="$(capability_password "$IBEX_RUNTIME_LOGIN")" \
      IBEX_WORKER_DB_PASSWORD="$(capability_password "$IBEX_WORKER_LOGIN")" \
      IBEX_AUTH_DB_PASSWORD="$(capability_password "$IBEX_AUTH_LOGIN")" \
      IBEX_BOOTSTRAP_DB_PASSWORD="$(capability_password "$IBEX_BOOTSTRAP_LOGIN")" \
      go run ./infra/migrations/postgres/cmd/migrate -command provision
  )
}
