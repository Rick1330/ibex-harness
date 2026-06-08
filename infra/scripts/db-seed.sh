#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV_ENV="$ROOT_DIR/infra/compose/dev/.env.example"
SEED_SQL="$ROOT_DIR/infra/scripts/seed_dev.sql"

load_dev_defaults() {
  if [[ -f "$DEV_ENV" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$DEV_ENV"
    set +a
  fi
}

normalize_psql_dsn() {
  local dsn="$1"
  dsn="${dsn//postgresql+asyncpg:/postgres:}"
  dsn="${dsn//postgresql:/postgres:}"
  echo "$dsn"
}

extract_dsn_host() {
  local dsn="$1"
  local host=""
  if [[ "$dsn" =~ @([^:/?]+) ]]; then
    host="${BASH_REMATCH[1]}"
  elif [[ "$dsn" =~ ^postgres://([^:/?@]+) ]]; then
    host="${BASH_REMATCH[1]}"
  elif [[ "$dsn" =~ (^|[[:space:]])host=([^[:space:]]+) ]]; then
    host="${BASH_REMATCH[2]}"
  fi
  echo "$host"
}

refuse_non_local_seed() {
  if [[ "${IBEX_ENV:-}" == "production" ]]; then
    echo "refusing db-seed: IBEX_ENV=production"
    exit 1
  fi
  local dsn="$1"
  local host
  host="$(extract_dsn_host "$dsn")"
  if [[ -z "$host" ]]; then
    echo "refusing db-seed: cannot parse host from POSTGRES_DSN (fail closed)"
    echo "use a URL DSN with a known local host or libpq host= keyword"
    exit 1
  fi
  case "$host" in
    localhost|127.0.0.1|host.docker.internal|::1)
      return 0
      ;;
    *)
      echo "refusing db-seed: POSTGRES_DSN host '$host' does not look local"
      echo "override only if you know this is a dev database"
      exit 1
      ;;
  esac
}

if [[ -z "${POSTGRES_DSN:-}" ]]; then
  load_dev_defaults
fi

if [[ -z "${POSTGRES_DSN:-}" ]]; then
  export POSTGRES_DSN="postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
fi

PSQL_DSN="$(normalize_psql_dsn "$POSTGRES_DSN")"
refuse_non_local_seed "$PSQL_DSN"

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required for db-seed"
    exit 1
  fi
}

require_tool psql

echo "Seeding development database..."
psql "$PSQL_DSN" -v ON_ERROR_STOP=1 -f "$SEED_SQL"
echo ""
echo "  Dev org ID:    00000000-0000-0000-0000-000000000001"
echo "  Dev agent ID:  00000000-0000-0000-0000-000000000003"
echo "  Dev PAT:       ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY"
echo ""
echo "Export for testing:"
echo "  export IBEX_DEV_TOKEN=ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY"
