#!/usr/bin/env bash
# Full / diff / incr backup against MinIO-backed pgBackRest repo (4.P.5).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TYPE="${1:-full}"  # full|diff|incr

resolve_conf() {
  if [[ -n "${PGBACKREST_CONF:-}" ]]; then
    if [[ ! -f "$PGBACKREST_CONF" ]]; then
      echo "[backup] PGBACKREST_CONF set but file missing: $PGBACKREST_CONF" >&2
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
  echo "[backup] missing real pgbackrest.conf at $conf (do not use .example)" >&2
  exit 1
}

CONF="$(resolve_conf)"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
case "$TYPE" in
  full|diff|incr) ;;
  *) echo "usage: $0 full|diff|incr" >&2; exit 2 ;;
esac

STATE_DIR="${IBEX_BACKUP_STATE_DIR:-/var/lib/ibex/backup}"
mkdir -p "$STATE_DIR"
chmod 0755 "$STATE_DIR"

echo "[backup] type=$TYPE stanza=$STANZA conf=$CONF"
pgbackrest --config="$CONF" --stanza="$STANZA" backup --type="$TYPE"
pgbackrest --config="$CONF" --stanza="$STANZA" info

STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
UNIX="$(date +%s)"

# Atomic writes into owner-controlled state dir (no symlink-follow tee to /tmp).
stamp_tmp="$(mktemp "$STATE_DIR/.stamp.XXXXXX")"
metrics_tmp="$(mktemp "$STATE_DIR/.metrics.XXXXXX")"
cleanup() {
  rm -f "$stamp_tmp" "$metrics_tmp"
}
trap cleanup EXIT

printf '[backup] ok %s\n' "$STAMP" >"$stamp_tmp"
mv -T "$stamp_tmp" "$STATE_DIR/ibex-last-backup.txt"

cat >"$metrics_tmp" <<EOF
# HELP ibex_postgres_last_backup_unixtime Unix time of last successful Postgres backup
# TYPE ibex_postgres_last_backup_unixtime gauge
ibex_postgres_last_backup_unixtime $UNIX
EOF
mv -T "$metrics_tmp" "$STATE_DIR/ibex_backup_metrics.prom"
trap - EXIT
