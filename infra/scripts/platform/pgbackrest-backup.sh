#!/usr/bin/env bash
# Full / diff / incr backup against MinIO-backed pgBackRest repo (4.P.5).
set -euo pipefail
TYPE="${1:-full}"  # full|diff|incr
CONF="${PGBACKREST_CONF:-infra/backup/pgbackrest/pgbackrest.conf}"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
case "$TYPE" in
  full|diff|incr) ;;
  *) echo "usage: $0 full|diff|incr" >&2; exit 2 ;;
esac
echo "[backup] type=$TYPE stanza=$STANZA conf=$CONF"
pgbackrest --config="$CONF" --stanza="$STANZA" backup --type="$TYPE"
pgbackrest --config="$CONF" --stanza="$STANZA" info
echo "[backup] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee /tmp/ibex-last-backup.txt
