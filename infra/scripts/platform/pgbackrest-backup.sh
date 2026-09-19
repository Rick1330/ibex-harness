#!/usr/bin/env bash
# Full / diff / incr backup against MinIO-backed pgBackRest repo (4.P.5).
set -euo pipefail
TYPE="${1:-full}"  # full|diff|incr
if [[ -n "${PGBACKREST_CONF:-}" ]]; then
  CONF="$PGBACKREST_CONF"
elif [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  CONF=infra/backup/pgbackrest/pgbackrest.conf
else
  CONF=infra/backup/pgbackrest/pgbackrest.conf.example
fi
STANZA="${PGBACKREST_STANZA:-ibex-main}"
case "$TYPE" in
  full|diff|incr) ;;
  *) echo "usage: $0 full|diff|incr" >&2; exit 2 ;;
esac
echo "[backup] type=$TYPE stanza=$STANZA conf=$CONF"
pgbackrest --config="$CONF" --stanza="$STANZA" backup --type="$TYPE"
pgbackrest --config="$CONF" --stanza="$STANZA" info
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
UNIX="$(date +%s)"
echo "[backup] ok $STAMP" | tee /tmp/ibex-last-backup.txt
# Prometheus textfile / pushgateway metric for freshness alert (≤5m RPO).
METRICS_DIR="${IBEX_BACKUP_METRICS_DIR:-/tmp}"
mkdir -p "$METRICS_DIR"
cat >"$METRICS_DIR/ibex_backup_metrics.prom" <<EOF
# HELP ibex_postgres_last_backup_unixtime Unix time of last successful Postgres backup
# TYPE ibex_postgres_last_backup_unixtime gauge
ibex_postgres_last_backup_unixtime $UNIX
EOF
