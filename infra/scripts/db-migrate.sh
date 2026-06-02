#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV_ENV="$ROOT_DIR/infra/compose/dev/.env.example"
CMD="${1:-up}"

load_dev_defaults() {
  if [[ -f "$DEV_ENV" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$DEV_ENV"
    set +a
  fi
}

if [[ -z "${POSTGRES_MIGRATE_DSN:-}" && -z "${POSTGRES_DSN:-}" ]]; then
  load_dev_defaults
fi

if [[ -z "${POSTGRES_MIGRATE_DSN:-}" && -z "${POSTGRES_DSN:-}" ]]; then
  export POSTGRES_MIGRATE_DSN="postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
fi

case "$CMD" in
  up|down|version)
    cd "$ROOT_DIR"
    go run ./infra/migrations/postgres/cmd/migrate -command "$CMD"
    ;;
  *)
    echo "usage: db-migrate.sh up|down|version"
    exit 2
    ;;
esac
