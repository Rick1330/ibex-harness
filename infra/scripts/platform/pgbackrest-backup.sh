#!/usr/bin/env bash
# Full / diff / incr backup (and repository check) for the S3-backed
# pgBackRest repository (4.P.5).
#
# The backup runs wherever the cluster is: the v1-single-node postgres image
# carries pgBackRest, so the caller passes PGBACKREST_EXEC_CONTAINER and the
# command is executed inside that container. A host without the binary falls
# back to a local `pgbackrest` (the development drill path).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TYPE="${1:-full}"  # full|diff|incr|check|stanza-create

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

# container_cli picks the engine that owns the containers. An explicit
# IBEX_CONTAINER_CLI wins; otherwise the first engine that answers wins, with
# docker preferred so CI keeps its existing behaviour.
container_cli() {
  if [[ -n "${IBEX_CONTAINER_CLI:-}" ]]; then
    printf '%s\n' "$IBEX_CONTAINER_CLI"
    return
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    printf 'docker\n'
    return
  fi
  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    printf 'podman\n'
    return
  fi
  printf 'docker\n'
}

CONF="$(resolve_conf)"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
case "$TYPE" in
  full|diff|incr|check|stanza-create) ;;
  *) echo "usage: $0 full|diff|incr|check|stanza-create" >&2; exit 2 ;;
esac

EXEC_CONTAINER="${PGBACKREST_EXEC_CONTAINER:-}"
CONTAINER_CONF="${PGBACKREST_CONTAINER_CONF:-/etc/pgbackrest/pgbackrest.conf}"
CLI=""
if [[ -n "$EXEC_CONTAINER" ]]; then
  CLI="$(container_cli)"
  if ! "$CLI" exec --user postgres "$EXEC_CONTAINER" pgbackrest version >/dev/null 2>&1; then
    echo "[backup] $EXEC_CONTAINER has no usable pgbackrest; refusing to run" >&2
    exit 1
  fi
elif ! command -v pgbackrest >/dev/null 2>&1; then
  echo "[backup] no pgbackrest on the host and PGBACKREST_EXEC_CONTAINER is unset" >&2
  exit 1
fi

# Every command goes through this wrapper so the container path and the host
# path stay one code path. The container inherits the PGBACKREST_* repository
# credentials from its environment (compose sets them), so they are never put
# on a command line.
run_pgbackrest() {
  if [[ -n "$EXEC_CONTAINER" ]]; then
    "$CLI" exec --user postgres "$EXEC_CONTAINER" \
      pgbackrest --config="$CONTAINER_CONF" --stanza="$STANZA" "$@"
  else
    pgbackrest --config="$CONF" --stanza="$STANZA" "$@"
  fi
}

# The stanza must exist before any WAL can be archived. Creating it is
# idempotent, so a first `make v1-backup` on a fresh profile arms archiving and
# every later run is a no-op. Set PGBACKREST_SKIP_STANZA_CREATE=1 to skip.
if [[ "${PGBACKREST_SKIP_STANZA_CREATE:-0}" != "1" ]]; then
  echo "[backup] stanza-create (idempotent) stanza=$STANZA"
  run_pgbackrest stanza-create
fi

if [[ "$TYPE" == "stanza-create" ]]; then
  # Arming step for a fresh profile: no backup, no freshness metric.
  echo "[backup] stanza-create ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 0
fi

if [[ "$TYPE" == "check" ]]; then
  echo "[backup] check stanza=$STANZA"
  run_pgbackrest check
  echo "[backup] check ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 0
fi

# The freshness metric must not be written for a dry run: a check is not a
# backup.
STATE_DIR="${IBEX_BACKUP_STATE_DIR:-}"
if [[ -z "$STATE_DIR" ]]; then
  if [[ "$(id -u)" -eq 0 || -d /var/lib/ibex/backup ]]; then
    STATE_DIR=/var/lib/ibex/backup
  else
    STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/ibex/backup"
  fi
fi
mkdir -p "$STATE_DIR"
chmod 0755 "$STATE_DIR"

echo "[backup] type=$TYPE stanza=$STANZA conf=$CONF"
run_pgbackrest backup --type="$TYPE"
run_pgbackrest info

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

cat >"$metrics_tmp" <<METRICS
# HELP ibex_postgres_last_backup_unixtime Unix time of last successful Postgres backup
# TYPE ibex_postgres_last_backup_unixtime gauge
ibex_postgres_last_backup_unixtime $UNIX
METRICS
mv -T "$metrics_tmp" "$STATE_DIR/ibex_backup_metrics.prom"
trap - EXIT

echo "[backup] state dir=$STATE_DIR"
