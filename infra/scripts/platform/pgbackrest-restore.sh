#!/usr/bin/env bash
# Restore Postgres from pgBackRest (4.P.5).
#
# Two modes:
#   latest        restore the newest backup, no recovery target (destructive:
#                 the live Postgres is stopped first)
#   point-in-time set PGBACKREST_RESTORE_TARGET to an ISO8601 timestamp; the
#                 restore passes --type=time --target=... --target-action=promote
#                 and recovery stops at that moment, not at the end of WAL.
#
# PGBACKREST_RESTORE_SCRATCH_VOLUME restores into a separate named volume and
# leaves the live cluster running. That is the drill path: it is the only way to
# prove a time target without destroying the running database.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

resolve_conf() {
  if [[ -n "${PGBACKREST_CONF:-}" && ! -f "${PGBACKREST_CONF}" ]]; then
    echo "[restore] PGBACKREST_CONF set but file missing: $PGBACKREST_CONF" >&2
    exit 1
  fi
  if [[ -n "${PGBACKREST_CONF:-}" ]]; then
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

# container_cli picks the engine that owns the containers; IBEX_CONTAINER_CLI
# overrides it. docker is preferred so CI behaviour does not change.
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

# The engine may be multi-word (`sudo -n podman` for a rootful store), so it is
# split into an argv array and every call expands the array. `compose` uses the
# same engine, which keeps the compose metadata lookup and the container calls
# in the same store.
CLI=()
read -r -a CLI <<<"$(container_cli)"

compose() {
  "${CLI[@]}" compose "$@"
}

# Resolve docker-compose named volume from Compose metadata only (fail closed).
# Never pick an arbitrary docker volume ls suffix match.
resolve_compose_volume() {
  local compose_file="$1"
  local vol=""

  if [[ -n "${PGBACKREST_COMPOSE_VOLUME:-}" ]]; then
    if ! "${CLI[@]}" volume inspect "$PGBACKREST_COMPOSE_VOLUME" >/dev/null 2>&1; then
      echo "[restore] PGBACKREST_COMPOSE_VOLUME set but volume missing: $PGBACKREST_COMPOSE_VOLUME" >&2
      return 1
    fi
    printf '%s\n' "$PGBACKREST_COMPOSE_VOLUME"
    return 0
  fi

  vol="$(
    compose -f "$compose_file" config --format json 2>/dev/null | python3 -c '
import json, sys
cfg = json.load(sys.stdin)
vols = cfg.get("volumes") or {}
svc = (cfg.get("services") or {}).get("postgres") or {}

def emit(key: str) -> None:
    meta = vols.get(key) or {}
    name = meta.get("name") if isinstance(meta, dict) else None
    print(name or key)
    raise SystemExit(0)

for m in svc.get("volumes") or []:
    if isinstance(m, dict):
        target = (m.get("target") or "").rstrip("/")
        source = m.get("source") or ""
        if target.endswith("postgresql/data") and source:
            emit(source)
    elif isinstance(m, str) and ":/var/lib/postgresql/data" in m:
        emit(m.split(":", 1)[0])

if "ibex_postgres_data" in vols:
    emit("ibex_postgres_data")
raise SystemExit(1)
'
  )" || true

  if [[ -z "$vol" ]]; then
    echo "[restore] could not resolve postgres volume from Compose metadata; set PGBACKREST_COMPOSE_VOLUME" >&2
    return 1
  fi
  if ! "${CLI[@]}" volume inspect "$vol" >/dev/null 2>&1; then
    echo "[restore] Compose volume name $vol does not exist locally; set PGBACKREST_COMPOSE_VOLUME" >&2
    return 1
  fi
  printf '%s\n' "$vol"
}

# Compose project network so repo1-s3-endpoint resolves. Prefer the object
# store container: it is the service that has to be reachable from the restore
# container.
resolve_compose_network() {
  local compose_file="$1"
  local cid
  local net
  cid="$(compose -f "$compose_file" ps -q objectstore 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    cid="$(compose -f "$compose_file" ps -q minio 2>/dev/null || true)"
  fi
  if [[ -z "$cid" ]]; then
    cid="$(compose -f "$compose_file" ps -aq 2>/dev/null | head -n1 || true)"
  fi
  if [[ -z "$cid" ]]; then
    echo "[restore] could not resolve compose network (no containers)" >&2
    return 1
  fi
  # One network name per line; take the first only (avoid concatenated names).
  net="$("${CLI[@]}" inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$cid" | head -n1 | tr -d '\r')"
  if [[ -z "$net" ]]; then
    echo "[restore] container $cid has no networks" >&2
    return 1
  fi
  printf '%s\n' "$net"
}

CONF="$(resolve_conf)"
STANZA="${PGBACKREST_STANZA:-ibex-main}"
# The path pgBackRest reads inside the restore container. The selected host
# config is mounted at exactly this path, so a custom PGBACKREST_CONF is the one
# the container reads (the backup path verifies the same agreement).
CONTAINER_CONF="${PGBACKREST_CONTAINER_CONF:-/etc/pgbackrest/pgbackrest.conf}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/infra/compose/dev/docker-compose.yml}"
TARGET="${PGBACKREST_PGDATA:-}"
IMAGE="${PGBACKREST_IMAGE:-pgbackrest/pgbackrest:2.53}"
RESTORE_USER="${PGBACKREST_RESTORE_USER:-}"
SCRATCH_VOLUME="${PGBACKREST_RESTORE_SCRATCH_VOLUME:-}"
RESTORE_TARGET="${PGBACKREST_RESTORE_TARGET:-}"
stopped=false
stopped_via_compose=false
COMPOSE_VOLUME=""

# A recovery target is passed to pgBackRest as an option value, so it is
# validated as an ISO8601 timestamp rather than forwarded verbatim.
#
# pgBackRest's --target parser is not ISO8601: it wants `YYYY-MM-DD HH:MM:SS`
# with optional milliseconds and optional `+HH[:MM]` offset, and rejects the
# `T` separator and `Z` suffix that an operator types. Validate the ISO8601
# form, then normalise it to the shape pgBackRest accepts so the documented
# `2026-11-14T09:01:00Z` input works instead of failing deep in the restore.
if [[ -n "$RESTORE_TARGET" ]]; then
  if ! [[ "$RESTORE_TARGET" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[T\ ][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}(:?[0-9]{2})?)?$ ]]; then
    echo "[restore] PGBACKREST_RESTORE_TARGET is not an ISO8601 timestamp: $RESTORE_TARGET" >&2
    exit 2
  fi
  iso_target="$RESTORE_TARGET"
  RESTORE_TARGET="${iso_target/T/ }"
  if [[ "$RESTORE_TARGET" == *Z ]]; then
    RESTORE_TARGET="${RESTORE_TARGET%Z}+00"
  fi
  echo "[restore] point-in-time target=$RESTORE_TARGET (from $iso_target; --type=time --target-action=promote)"
fi

restore_args=()
if [[ -n "$RESTORE_TARGET" ]]; then
  restore_args+=(--type=time --target="$RESTORE_TARGET" --target-action=promote)
fi

# --delta belongs to the destructive branch only. pgBackRest refuses to restore
# into a non-empty pg1-path, and the live data directory is non-empty by
# definition, so without --delta the command aborts *after* Postgres has been
# stopped: the profile is left down and no data is restored. --delta lets
# pgBackRest reconcile the existing directory instead (it removes files that are
# not in the backup), which is safe only because the cluster was cleanly stopped
# above and nothing is writing to the directory. The scratch path restores into
# a fresh, empty volume, so it must not carry --delta.
destructive_restore_args=("${restore_args[@]}" --delta)

# pgBackRest reads the repository credentials from the environment; never put
# them on a command line.
run_args=()
cred_vars=()
if [[ -n "$RESTORE_USER" ]]; then
  run_args+=(--user "$RESTORE_USER")
fi
for var in PGBACKREST_REPO1_CIPHER_PASS PGBACKREST_REPO1_S3_KEY PGBACKREST_REPO1_S3_KEY_SECRET; do
  if [[ -n "${!var:-}" ]]; then
    run_args+=(-e "$var")
    cred_vars+=("$var")
  fi
done

# print_credential_load prints the loading step that belongs above the printed
# start command. `-e VAR` forwards the value the *operator's* shell holds, and
# the environment that ran this script does not survive into that shell: a bare
# shell forwards an empty value and recovery then dies with
# "archive-get command requires option: repo1-cipher-pass".
#
# The values are read from the profile .env (mode 0600) with the repository's
# Compose-dotenv reader, which reproduces what `make v1-restore` and
# `make v1-pitr` export. No value is printed and none is placed on a command
# line: the assignments run command substitution over a redirected file.
print_credential_load() {
  local var source_key
  (( ${#cred_vars[@]} )) || return 0
  cat <<'LOAD'
The start command forwards the repository credentials by name (-e VAR), so the
shell that runs it must hold the values; `make v1-restore` and `make v1-pitr`
export them from the profile .env before running this script. To start the
cluster by hand, load the same values the same way — nothing below prints a
value or puts one on a command line:
LOAD
  printf '\n  ENV_FILE="${IBEX_V1_ENV:-%s/infra/compose/v1-single-node/.env}"\n' "$ROOT"
  printf '  ibex_env_value() { python3 %s/infra/scripts/lib/dotenv.py "$1" < "$ENV_FILE"; }\n' "$ROOT"
  for var in "${cred_vars[@]}"; do
    case "$var" in
      PGBACKREST_REPO1_S3_KEY) source_key=IBEX_OBJECTSTORE_ACCESS_KEY ;;
      PGBACKREST_REPO1_S3_KEY_SECRET) source_key=IBEX_OBJECTSTORE_SECRET_KEY ;;
      *) source_key="$var" ;;
    esac
    printf '  %s="$(ibex_env_value %s)"\n' "$var" "$source_key"
    printf '  : "${%s:?empty; check $ENV_FILE}"\n' "$var"
  done
  printf '  export %s\n\n' "${cred_vars[*]}"
}

if [[ -n "$SCRATCH_VOLUME" ]]; then
  # Drill path: restore beside the live cluster. Nothing is stopped, and the
  # live data directory is never mounted.
  if ! "${CLI[@]}" volume inspect "$SCRATCH_VOLUME" >/dev/null 2>&1; then
    echo "[restore] scratch volume $SCRATCH_VOLUME does not exist; create it first" >&2
    exit 1
  fi
  NETWORK="$(resolve_compose_network "$COMPOSE_FILE")"
  echo "[restore] scratch restore volume=$SCRATCH_VOLUME network=$NETWORK image=$IMAGE"
  "${CLI[@]}" run --rm "${run_args[@]}" \
    --network "$NETWORK" \
    -v "${SCRATCH_VOLUME}:/var/lib/postgresql/data" \
    -v "${CONF}:${CONTAINER_CONF}:ro" \
    "$IMAGE" \
    pgbackrest --config="$CONTAINER_CONF" \
      --stanza="$STANZA" --pg1-path=/var/lib/postgresql/data "${restore_args[@]}" restore
  echo "[restore] scratch restore ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat <<NEXT

The restored cluster is not running. Start it on the scratch volume, with
archiving disabled so the restored timeline cannot write into the live
repository, then verify the recovery point.

$(print_credential_load)
  ${CLI[*]} run -d --name ibex-pitr-scratch --network $NETWORK ${run_args[*]} \\
    -v $SCRATCH_VOLUME:/var/lib/postgresql/data \\
    -v $CONF:$CONTAINER_CONF:ro \\
    $IMAGE postgres -c archive_mode=off

  ${CLI[*]} exec ibex-pitr-scratch psql -U ibex -d ibex \\
    -c 'SELECT pg_is_in_recovery(), pg_last_xact_replay_timestamp()'
NEXT
  exit 0
fi

echo "[restore] stopping Postgres before restore"
if command -v "${CLI[0]}" >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]] \
  && compose -f "$COMPOSE_FILE" stop postgres 2>/dev/null; then
  stopped=true
  stopped_via_compose=true
fi

if [[ -z "$TARGET" && "$stopped_via_compose" == "true" ]]; then
  COMPOSE_VOLUME="$(resolve_compose_volume "$COMPOSE_FILE")"
  TARGET="/var/lib/postgresql/data"
  echo "[restore] using compose volume=$COMPOSE_VOLUME container path TARGET=$TARGET"
elif [[ -z "$TARGET" ]]; then
  TARGET="/var/lib/postgresql/data"
fi

if command -v pg_ctl >/dev/null 2>&1 && [[ -d "$TARGET" ]] \
  && pg_ctl -D "$TARGET" stop -m fast 2>/dev/null; then
  stopped=true
fi
if [[ "$stopped" != "true" && "${PGBACKREST_ALLOW_UNSAFE_RESTORE:-0}" != "1" ]]; then
  echo "[restore] refused: could not stop Postgres (set PGBACKREST_ALLOW_UNSAFE_RESTORE=1 only for dry-run labs)" >&2
  exit 1
fi

# verify_destructive_restore_compose proves the restore produced a usable
# cluster before anything is reported as ok.
#
# The order matters: the postgres entrypoint runs initdb when PGDATA is empty,
# so starting the container first would turn a failed restore into a fresh
# cluster that passes every liveness check. PG_VERSION is therefore verified
# before the server is started, through a throwaway read-only container over the
# same volume (the restore ran as uid 999, so the operator's shell cannot read
# the directory directly). Only then is the server started and asked for
# pg_is_in_recovery(), which the restore must have left false: the destructive
# branch either completes crash recovery (latest) or reaches the recovery target
# and promotes (PITR, --target-action=promote).
verify_destructive_restore_compose() {
  local cid in_recovery=""
  if ! "${CLI[@]}" run --rm --entrypoint sh -v "${COMPOSE_VOLUME}:${TARGET}:ro" "$IMAGE" \
    -c "test -f ${TARGET}/PG_VERSION"; then
    echo "[restore] FAILED: ${TARGET}/PG_VERSION is missing on volume ${COMPOSE_VOLUME}; the restore did not produce a data directory" >&2
    return 1
  fi
  echo "[restore] data directory verified: ${TARGET}/PG_VERSION present"
  echo "[restore] starting Postgres to verify it leaves recovery"
  if ! compose -f "$COMPOSE_FILE" start postgres >/dev/null; then
    echo "[restore] FAILED: could not start postgres after restore" >&2
    return 1
  fi
  cid="$(compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null | head -n1 || true)"
  if [[ -z "$cid" ]]; then
    echo "[restore] FAILED: postgres container not found after restore" >&2
    return 1
  fi
  for _ in $(seq 1 120); do
    # POSTGRES_USER is the superuser created by the image; the container has it
    # in its environment, so the query never needs a value from this script.
    in_recovery="$("${CLI[@]}" exec "$cid" sh -c 'psql -U "$POSTGRES_USER" -d postgres -tAc "select pg_is_in_recovery()"' 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ "$in_recovery" == "f" ]]; then
      break
    fi
    sleep 1
  done
  if [[ "$in_recovery" != "f" ]]; then
    echo "[restore] FAILED: pg_is_in_recovery() is '${in_recovery:-no answer}' after 120s; the cluster did not leave recovery" >&2
    echo "[restore] inspect the server log with: ${CLI[*]} logs $cid" >&2
    return 1
  fi
  echo "[restore] recovery state verified: pg_is_in_recovery()=false"
  return 0
}

# canonical_dir resolves a directory to an absolute, symlink-free path so the
# connected server's data_directory can be compared with TARGET.
canonical_dir() {
  local dir="$1"
  ( cd "$dir" 2>/dev/null && pwd -P ) || printf '%s\n' "$dir"
}

# verify_destructive_restore_host is the same proof for a host data directory:
# PG_VERSION first (so an empty directory is never initialised into a false
# success), then the cluster is started and pg_is_in_recovery() is required to
# be false. A missing pg_ctl or psql fails closed: an unverified restore is not
# reported as ok.
#
# psql must target the restored server explicitly. `pg_ctl -D "$TARGET" start`
# starts whatever cluster owns $TARGET, which may listen on a non-default port;
# a bare `psql` would use the default socket/port and can reach a different
# cluster, reporting its recovery state. The port and socket directory are read
# from the restored postmaster's own postmaster.pid, and the server's
# data_directory is compared with $TARGET before the result is accepted.
verify_destructive_restore_host() {
  local in_recovery="" pidfile pg_port pg_socket actual_data_dir
  local -a psql_target=()
  if [[ ! -f "$TARGET/PG_VERSION" ]]; then
    echo "[restore] FAILED: $TARGET/PG_VERSION is missing; the restore did not produce a data directory" >&2
    return 1
  fi
  echo "[restore] data directory verified: $TARGET/PG_VERSION present"
  if ! command -v pg_ctl >/dev/null 2>&1; then
    echo "[restore] FAILED: pg_ctl is not available, so the restored cluster cannot be started and pg_is_in_recovery() cannot be proven" >&2
    return 1
  fi
  if ! command -v psql >/dev/null 2>&1; then
    echo "[restore] FAILED: psql is not available, so the restored cluster cannot be queried" >&2
    return 1
  fi
  if ! pg_ctl -D "$TARGET" -w -t 120 start >/dev/null; then
    echo "[restore] FAILED: pg_ctl could not start the restored cluster at $TARGET" >&2
    return 1
  fi
  pidfile="$TARGET/postmaster.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "[restore] FAILED: $pidfile is missing after pg_ctl start; cannot identify the restored server" >&2
    return 1
  fi
  pg_port="$(sed -n '4p' "$pidfile" | tr -d '[:space:]')"
  pg_socket="$(sed -n '5p' "$pidfile" | tr -d '\r')"
  if [[ -z "$pg_port" ]]; then
    echo "[restore] FAILED: could not read the port from $pidfile" >&2
    return 1
  fi
  # A relative socket directory is relative to the data directory.
  if [[ -n "$pg_socket" && "$pg_socket" != /* ]]; then
    pg_socket="$TARGET/$pg_socket"
  fi
  psql_target=(-p "$pg_port")
  if [[ -n "$pg_socket" ]]; then
    psql_target+=(-h "$pg_socket")
  else
    # TCP-only cluster: connect to this host on the port it actually bound.
    psql_target+=(-h 127.0.0.1)
  fi
  for _ in $(seq 1 120); do
    in_recovery="$(psql "${psql_target[@]}" -d postgres -tAc 'select pg_is_in_recovery()' 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ "$in_recovery" == "f" ]]; then
      break
    fi
    sleep 1
  done
  if [[ "$in_recovery" != "f" ]]; then
    echo "[restore] FAILED: pg_is_in_recovery() is '${in_recovery:-no answer}' after 120s; the cluster did not leave recovery" >&2
    return 1
  fi
  # A port and socket identify a server, not necessarily the restored one:
  # another cluster could own the same port if the restored one failed to bind.
  # Compare the server's data_directory with TARGET before accepting the result.
  actual_data_dir="$(psql "${psql_target[@]}" -d postgres -tAc 'show data_directory' 2>/dev/null | tr -d '\r' || true)"
  if [[ -z "$actual_data_dir" || "$(canonical_dir "$actual_data_dir")" != "$(canonical_dir "$TARGET")" ]]; then
    echo "[restore] FAILED: connected server data_directory='${actual_data_dir:-no answer}' does not match TARGET=$TARGET" >&2
    return 1
  fi
  echo "[restore] recovery state verified: pg_is_in_recovery()=false (data_directory=$actual_data_dir)"
  return 0
}

echo "[restore] stanza=$STANZA target=$TARGET conf=$CONF"
if [[ "$stopped_via_compose" == "true" && -n "$COMPOSE_VOLUME" ]]; then
  # Host pgbackrest cannot resolve the object store; run inside the compose
  # network.
  NETWORK="$(resolve_compose_network "$COMPOSE_FILE")"
  echo "[restore] running pgbackrest in compose network=$NETWORK image=$IMAGE"
  "${CLI[@]}" run --rm "${run_args[@]}" \
    --network "$NETWORK" \
    -v "${COMPOSE_VOLUME}:${TARGET}" \
    -v "${CONF}:${CONTAINER_CONF}:ro" \
    "$IMAGE" \
    pgbackrest --config="$CONTAINER_CONF" \
      --stanza="$STANZA" --pg1-path="$TARGET" "${destructive_restore_args[@]}" restore
  verify_destructive_restore_compose
else
  pgbackrest --config="$CONF" --stanza="$STANZA" --pg1-path="$TARGET" "${destructive_restore_args[@]}" restore
  verify_destructive_restore_host
fi
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
