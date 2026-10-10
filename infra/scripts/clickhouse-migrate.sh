#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV_DIR="$ROOT_DIR/infra/compose/dev"
CMD="${1:-up}"

load_dev_defaults() {
  local env_file=""
  if [[ -f "$DEV_DIR/.env" ]]; then
    env_file="$DEV_DIR/.env"
  elif [[ -f "$DEV_DIR/.env.example" ]]; then
    env_file="$DEV_DIR/.env.example"
  else
    return 0
  fi
  # shellcheck disable=SC1090
  set -a
  source "$env_file"
  set +a
}

if [[ -z "${CLICKHOUSE_MIGRATE_DSN:-}" && -z "${CLICKHOUSE_DSN:-}" ]]; then
  load_dev_defaults
fi

if [[ -z "${CLICKHOUSE_MIGRATE_DSN:-}" && -z "${CLICKHOUSE_DSN:-}" ]]; then
  export CLICKHOUSE_MIGRATE_DSN="clickhouse://default:@localhost:9002?database=ibex&x-multi-statement=true&x-migrations-table-engine=MergeTree"
fi

CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}"
CLICKHOUSE_DB="${CLICKHOUSE_DB:-ibex}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-default}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
if [[ ! "$CLICKHOUSE_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "clickhouse migrate: invalid CLICKHOUSE_DB identifier" >&2
  exit 2
fi

netrc_file="$(mktemp)"
trap 'rm -f "$netrc_file"' EXIT
chmod 600 "$netrc_file"
printf 'machine 127.0.0.1 login %s password %s\n' "$CLICKHOUSE_USER" "$CLICKHOUSE_PASSWORD" >"$netrc_file"
curl -fsS --retry 10 --retry-delay 1 --netrc-file "$netrc_file" \
  --data-binary "CREATE DATABASE IF NOT EXISTS \`$CLICKHOUSE_DB\`" \
  "http://127.0.0.1:${CLICKHOUSE_HTTP_PORT}/" >/dev/null

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
