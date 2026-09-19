#!/usr/bin/env bash
# Restore Postgres from pgBackRest (4.P.5). Destructive — stop PG first.
set -euo pipefail
if [[ -n "${PGBACKREST_CONF:-}" ]]; then
  CONF="$PGBACKREST_CONF"
elif [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  CONF=infra/backup/pgbackrest/pgbackrest.conf
else
  CONF=infra/backup/pgbackrest/pgbackrest.conf.example
fi
STANZA="${PGBACKREST_STANZA:-ibex-main}"
TARGET="${PGBACKREST_PGDATA:-/var/lib/postgresql/data}"
echo "[restore] stanza=$STANZA target=$TARGET conf=$CONF"
pgbackrest --config="$CONF" --stanza="$STANZA" --pg1-path="$TARGET" restore
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
