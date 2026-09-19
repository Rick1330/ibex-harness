#!/usr/bin/env bash
# Restore Postgres from pgBackRest (4.P.5). Destructive — stop PG first.
set -euo pipefail
CONF="${PGBACKREST_CONF:-infra/backup/pgbackrest/pgbackrest.conf}"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
TARGET="${PGBACKREST_PGDATA:-/var/lib/postgresql/data}"
echo "[restore] stanza=$STANZA target=$TARGET"
pgbackrest --config="$CONF" --stanza="$STANZA" --pg1-path="$TARGET" restore
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
