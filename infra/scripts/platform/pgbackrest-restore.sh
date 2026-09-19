#!/usr/bin/env bash
# Restore Postgres from pgBackRest (4.P.5). Destructive — stop PG first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

resolve_conf() {
  if [[ -n "${PGBACKREST_CONF:-}" ]]; then
    if [[ ! -f "$PGBACKREST_CONF" ]]; then
      echo "[restore] PGBACKREST_CONF set but file missing: $PGBACKREST_CONF" >&2
      exit 1
    fi
    printf '%s\n' "$PGBACKREST_CONF"
    return
  fi
  local conf="$ROOT/infra/backup/pgbackrest/pgbackrest.conf"
  if [[ -f "$conf" ]]; then
    printf '%s\n' "$conf"
    return
  fi
  echo "[restore] missing real pgbackrest.conf at $conf (do not use .example)" >&2
  exit 1
}

CONF="$(resolve_conf)"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
TARGET="${PGBACKREST_PGDATA:-/var/lib/postgresql/data}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/infra/compose/dev/docker-compose.yml}"

echo "[restore] stopping Postgres before restore"
stopped=false
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  if docker compose -f "$COMPOSE_FILE" stop postgres 2>/dev/null; then
    stopped=true
  fi
fi
if command -v pg_ctl >/dev/null 2>&1 && [[ -d "$TARGET" ]]; then
  if pg_ctl -D "$TARGET" stop -m fast 2>/dev/null; then
    stopped=true
  fi
fi
if [[ "$stopped" != "true" && "${PGBACKREST_ALLOW_UNSAFE_RESTORE:-0}" != "1" ]]; then
  echo "[restore] refused: could not stop Postgres (set PGBACKREST_ALLOW_UNSAFE_RESTORE=1 only for dry-run labs)" >&2
  exit 1
fi

echo "[restore] stanza=$STANZA target=$TARGET conf=$CONF"
pgbackrest --config="$CONF" --stanza="$STANZA" --pg1-path="$TARGET" restore
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
