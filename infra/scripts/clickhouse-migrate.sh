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

if [[ -z "${CLICKHOUSE_MIGRATE_DSN:-}" && -z "${CLICKHOUSE_DSN:-}" ]]; then
  load_dev_defaults
fi

if [[ -z "${CLICKHOUSE_MIGRATE_DSN:-}" && -z "${CLICKHOUSE_DSN:-}" ]]; then
  export CLICKHOUSE_MIGRATE_DSN="clickhouse://default:@localhost:9002?database=ibex&x-multi-statement=true&x-migrations-table-engine=MergeTree"
fi

case "$CMD" in
  up|down|version)
    cd "$ROOT_DIR"
    go run ./infra/migrations/clickhouse/cmd/migrate -command "$CMD"
    ;;
  *)
    echo "usage: clickhouse-migrate.sh up|down|version"
    exit 2
    ;;
esac
