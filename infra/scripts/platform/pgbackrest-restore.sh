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
#
# Repository credentials reach the restore container through a 0600 environment
# file passed with --env-file, never through `-e VAR` and never on a command
# line. With a rootful engine (`sudo -n podman`, IBEX_PODMAN_SUDO=1) sudo's
# env_reset drops the exported values before the engine starts, so a name-only
# `-e` arrives empty and the restore fails after Postgres is already stopped.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../lib/pitr_time.sh
. "$ROOT/infra/scripts/lib/pitr_time.sh"

# Whitespace class for trimming a single psql -tA value. Defined once because
# every scalar read back from the cluster trims with the same pattern.
PG_WS_TRIM='[:space:]'

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
  return 1
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

# --- Point-in-time restore report (Stage 2 / P0-10) -------------------------
# `make v1-pitr` must leave an artefact, not only perform a restore. State is
# recorded as the run proceeds and written once, from the exit trap, so a run
# that dies half way still explains itself instead of leaving no report at all.
# The writer (infra/scripts/platform/pitr_report.sh) maps these onto the same
# schema the restore drill uses.
PITR_REPORT="${PGBACKREST_RESTORE_REPORT:-}"
PITR_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PITR_ENVIRONMENT_CLASS="${IBEX_DRILL_ENVIRONMENT_CLASS:-}"
PITR_MECHANISM="pgbackrest_wal"
PITR_BACKUP_OK=false
PITR_RESTORE_OK=false
PITR_ATTEMPTED=false
# Which restore target this run actually used, set where the script commits to a
# branch: `scratch` for the volume it restores beside the live cluster, `host`
# for the real data directory. It is a producer fact, not an environment
# variable, so the report records the branch the run took rather than what a
# caller claimed.
PITR_RESTORE_TARGET=""
PITR_WAL_ARCHIVE_OK=false
# The archive counters are diagnostics beside the bound, never the bound itself:
# the upload age is when an upload *completed*, not the transaction time the
# segment it carried covers, so a draining backlog can make it look fresh.
PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC=""
PITR_WAL_ARCHIVE_LAST_SEGMENT=""
PITR_WAL_ARCHIVE_CURRENT_SEGMENT=""
PITR_WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE=""
# The cluster's archive_timeout and wal_segment_size travel with the counters so
# an operator reading a miss has the numbers.
PITR_WAL_ARCHIVE_TIMEOUT_SEC=""
PITR_WAL_ARCHIVE_WAL_SEGMENT_SIZE=""
# The older-segment count is not measured. PostgreSQL retains already-archived
# segments in pg_wal until recycling, so a positive count of segments older than
# last_archived_wal does not mean they are pending archival: a healthy PITR run
# reported a backlog until those files were recycled. The continuity proof is the
# restore itself, which replays every segment from the backup to the replay
# point, so this report records wal_archive_backlog: null because the continuity
# input is not measurable.

# Record the requested target immediately: a run blocked before the target is
# parsed must still say which recovery point was asked for.
PITR_TARGET_TIMESTAMP="${PGBACKREST_RESTORE_TARGET:-}"
PITR_RECOVERY_TARGET_REACHED=""
PITR_RECOVERY_REPLAY_TIMESTAMP=""
# The instant archiving stopped. Once the primary is stopped nothing new is
# archived, so the newest recoverable commit is frozen here; the RPO upper bound
# is the gap between this instant and what the restored cluster replayed. It is
# recorded only when a stop actually happened, so a run that restored beside a
# live primary (the scratch path) and an unsafe run whose stop failed both leave
# it empty and can claim no RPO.
PITR_WAL_ARCHIVE_QUIESCED_AT=""
PITR_CLUSTER_DATA_BYTES=""
PITR_RESTORED_ORGS=""
PITR_RESTORED_MEMORIES=""
PITR_BLOCKED_BY=""
PITR_VERIFY_CONTAINER=""

# pitr_environment_class names where the run happened, so a committed report is
# never mistaken for a hosted result.
pitr_environment_class() {
  if [[ -n "$PITR_ENVIRONMENT_CLASS" ]]; then
    printf '%s\n' "$PITR_ENVIRONMENT_CLASS"
    return 0
  fi
  local engine="${CLI[0]:-unknown}" mode=compose
  if [[ -n "${SCRATCH_VOLUME:-}" ]]; then
    mode=scratch
  fi
  printf 'local-%s-%s\n' "$engine" "$mode"
}

# pitr_blocked records why PITR could not be performed at all. A run stopped by
# a precondition reports `mechanism: unavailable` with this reason; the report
# writer refuses an unavailable report that carries no reason.
pitr_blocked() {
  PITR_MECHANISM=unavailable
  PITR_BLOCKED_BY="$1"
  echo "[restore] PITR blocked: $1" >&2
}

# pitr_failed records why an *attempted* restore did not succeed. Unlike
# pitr_blocked it leaves the mechanism alone: pgBackRest was available and was
# used, the restore simply failed. blocked_by carries the reason either way, so
# the artefact a failed run leaves behind says what went wrong.
pitr_failed() {
  PITR_BLOCKED_BY="$1"
  echo "[restore] PITR failed: $1" >&2
}

# prepare_pitr_report_path proves the report destination is writable before
# anything is stopped or restored. The point of the run is the artefact: a run
# whose evidence cannot be written has not achieved what it set out to do, and
# discovering that at exit — after the restore already happened — turns a
# successful recovery into an unexplained one.
prepare_pitr_report_path() {
  [[ -n "$PITR_REPORT" ]] || return 0
  local dir
  dir="$(dirname "$PITR_REPORT")"
  if ! mkdir -p "$dir" 2>/dev/null || [[ ! -w "$dir" ]]; then
    echo "[restore] FAILED: the report directory $dir cannot be created or written; nothing has been stopped" >&2
    return 1
  fi
  return 0
}

cleanup_pitr_verify_container() {
  if [[ -n "$PITR_VERIFY_CONTAINER" ]]; then
    "${CLI[@]}" rm -f "$PITR_VERIFY_CONTAINER" >/dev/null 2>&1 || true
    PITR_VERIFY_CONTAINER=""
  fi
}

# emit_fact writes one measured fact, and nothing at all when it was not
# measured: an absent key and an empty one would read the same to a caller, so
# only real values reach the file.
emit_fact() {
  [[ -n "$2" ]] || return 0
  printf '%s=%s\n' "$1" "$2"
}

# write_restore_facts records what this run measured for a caller that cannot
# read this shell — the restore drill, which owns its own report. The file is
# key=value: timestamps and counts only, never a credential, and writing it needs
# no network and no new dependency.
#
# It runs from the exit path, so a failed run still records what it measured; the
# caller decides what the facts support.
write_restore_facts() {
  local target="${PGBACKREST_RESTORE_FACTS_FILE:-}" tmp
  [[ -n "$target" ]] || return 0
  if ! mkdir -p "$(dirname "$target")" 2>/dev/null; then
    echo "[restore] WARNING: cannot create the directory for $target; the restore facts were not written" >&2
    return 0
  fi
  tmp="$target.$$"
  if ! {
    emit_fact wal_archive_quiesced_at "$PITR_WAL_ARCHIVE_QUIESCED_AT"
    emit_fact recovery_replay_timestamp "$PITR_RECOVERY_REPLAY_TIMESTAMP"
    emit_fact cluster_data_bytes "$PITR_CLUSTER_DATA_BYTES"
    emit_fact restored_orgs "$PITR_RESTORED_ORGS"
    emit_fact restored_memories "$PITR_RESTORED_MEMORIES"
  } >"$tmp" 2>/dev/null || ! mv -f "$tmp" "$target" 2>/dev/null; then
    rm -f -- "$tmp"
    echo "[restore] WARNING: could not write the restore facts to $target" >&2
  fi
  return 0
}

emit_pitr_report() {
  [[ -n "$PITR_REPORT" ]] || return 0
  PITR_REPORT="$PITR_REPORT" \
    PITR_STARTED_AT="$PITR_STARTED_AT" \
    PITR_ENVIRONMENT_CLASS="$(pitr_environment_class)" \
    PITR_MECHANISM="$PITR_MECHANISM" \
    PITR_BACKUP_OK="$PITR_BACKUP_OK" \
    PITR_RESTORE_OK="$PITR_RESTORE_OK" \
    PITR_RESTORE_TARGET="$PITR_RESTORE_TARGET" \
    PITR_WAL_ARCHIVE_OK="$PITR_WAL_ARCHIVE_OK" \
    PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC="$PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC" \
    PITR_WAL_ARCHIVE_LAST_SEGMENT="$PITR_WAL_ARCHIVE_LAST_SEGMENT" \
    PITR_WAL_ARCHIVE_CURRENT_SEGMENT="$PITR_WAL_ARCHIVE_CURRENT_SEGMENT" \
    PITR_WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE="$PITR_WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE" \
    PITR_WAL_ARCHIVE_TIMEOUT_SEC="$PITR_WAL_ARCHIVE_TIMEOUT_SEC" \
    PITR_WAL_ARCHIVE_WAL_SEGMENT_SIZE="$PITR_WAL_ARCHIVE_WAL_SEGMENT_SIZE" \
    PITR_TARGET_TIMESTAMP="$PITR_TARGET_TIMESTAMP" \
    PITR_RECOVERY_TARGET_REACHED="$PITR_RECOVERY_TARGET_REACHED" \
    PITR_RECOVERY_REPLAY_TIMESTAMP="$PITR_RECOVERY_REPLAY_TIMESTAMP" \
    PITR_WAL_ARCHIVE_QUIESCED_AT="$PITR_WAL_ARCHIVE_QUIESCED_AT" \
    PITR_CLUSTER_DATA_BYTES="$PITR_CLUSTER_DATA_BYTES" \
    PITR_RESTORED_ORGS="$PITR_RESTORED_ORGS" \
    PITR_RESTORED_MEMORIES="$PITR_RESTORED_MEMORIES" \
    PITR_BLOCKED_BY="$PITR_BLOCKED_BY" \
    bash "$ROOT/infra/scripts/platform/pitr_report.sh"
}

on_exit() {
  local status=$?
  if declare -F cleanup_cred_env_file >/dev/null; then
    cleanup_cred_env_file
  fi
  cleanup_pitr_verify_container
  write_restore_facts
  # Every failed exit must leave a report that says why, including the paths
  # that fail before a caller records a reason (network or volume discovery, a
  # refusal after Postgres was stopped). Without this the requested path is
  # absent — or, worse, still holds an earlier run's success.
  if [[ "$status" -ne 0 && "$PITR_RESTORE_OK" != "true" && -z "$PITR_BLOCKED_BY" ]]; then
    if [[ "$PITR_ATTEMPTED" == "true" ]]; then
      pitr_failed "the restore ran but did not complete; the run exited with status $status"
    else
      pitr_blocked "the run exited with status $status before the restore started"
    fi
  fi
  # A report that cannot be written is a failed run, not a quiet one: a run that
  # cannot produce evidence must not look like one that did. An earlier failure
  # keeps its status.
  if ! emit_pitr_report; then
    echo "[restore] ERROR: the PITR report writer failed for ${PITR_REPORT:-<unset>}; see the reason above" >&2
    if [[ "$status" -eq 0 ]]; then
      status=1
    fi
  fi
  exit "$status"
}
trap on_exit EXIT

if ! prepare_pitr_report_path; then
  pitr_blocked "the report directory for ${PITR_REPORT} cannot be created or written; nothing has been stopped"
  exit 2
fi

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

# resolve_conf runs in a subshell, so it cannot record the reason itself: the
# caller records it, in the shell that owns the exit trap and the report.
if ! CONF="$(resolve_conf)"; then
  pitr_blocked "the pgBackRest repository config is missing or refused (infra/backup/pgbackrest/pgbackrest.conf)"
  exit 1
fi
STANZA="${PGBACKREST_STANZA:-ibex-main}"
# The path pgBackRest reads inside the restore container. The selected host
# config is mounted at exactly this path, so a custom PGBACKREST_CONF is the one
# the container reads (the backup path verifies the same agreement).
CONTAINER_CONF="${PGBACKREST_CONTAINER_CONF:-/etc/pgbackrest/pgbackrest.conf}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/infra/compose/dev/docker-compose.yml}"
TARGET="${PGBACKREST_PGDATA:-}"
# Default to the image the profile actually builds. The upstream
# `pgbackrest/pgbackrest` namespace no longer publishes version tags, so a
# default pointing there fails at pull time on a direct script invocation.
IMAGE="${PGBACKREST_IMAGE:-ibex-v1-postgres:local}"
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
# with optional milliseconds and an offset, and rejects the `T` separator and `Z`
# suffix that an operator types. Validate the ISO8601 form, then normalise it to
# the shape pgBackRest accepts so the documented `2026-11-14T09:01:00Z` input
# works instead of failing deep in the restore.
#
# The offset is mandatory. A zone-less timestamp is not an instant: `date` reads
# it in the host's local time, pgBackRest reads it in the host's local time, and
# PostgreSQL applies its own TimeZone during recovery, so recovery can stop at
# one instant while the replay check compares against another — a false pass or a
# false miss depending on where the host's clock sits.
iso_target=""
target_micros=""
if [[ -n "$RESTORE_TARGET" ]]; then
  if ! [[ "$RESTORE_TARGET" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[T\ ][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}(:?[0-9]{2})?)$ ]]; then
    echo "[restore] PGBACKREST_RESTORE_TARGET is not an ISO8601 timestamp with an explicit UTC offset (Z, +HH, +HHMM or +HH:MM): $RESTORE_TARGET" >&2
    pitr_blocked "PGBACKREST_RESTORE_TARGET is not an ISO8601 timestamp with an explicit UTC offset (Z, +HH, +HHMM or +HH:MM); without one the host's local time decides which instant was asked for: $RESTORE_TARGET"
    exit 2
  fi
  iso_target="$RESTORE_TARGET"
  PITR_TARGET_TIMESTAMP="$iso_target"
  # Integer microseconds, not whole seconds: the replayed transaction is
  # compared against this value, and truncating it here is what made a replay
  # at .800 before a target at .900 fail.
  target_micros="$(iso_micros "$iso_target")"
  if [[ -z "$target_micros" ]]; then
    echo "[restore] PGBACKREST_RESTORE_TARGET could not be converted to an epoch: $iso_target" >&2
    pitr_blocked "PGBACKREST_RESTORE_TARGET could not be converted to an epoch: $iso_target"
    exit 2
  fi
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
#
# `--env-file` rather than `-e VAR`. A name-only `-e VAR` makes the engine
# import the value from *its own* environment, and with IBEX_PODMAN_SUDO=1 that
# environment is the one sudo built under its default env_reset: the exported
# values are gone, the import yields nothing, and the restore container starts
# without credentials. The failure appeared only after Postgres had been
# stopped. --env-file is read by the engine process itself, so delivery depends
# on neither sudo's environment nor the invoking shell. The file is created by
# mktemp at 0600 and removed by the EXIT trap; no value is printed and no value
# is placed on a command line.
CRED_NAMES=(PGBACKREST_REPO1_CIPHER_PASS PGBACKREST_REPO1_S3_KEY PGBACKREST_REPO1_S3_KEY_SECRET)

# credential_source_key maps a repository credential onto the key the v1 profile
# dotenv stores it under. The object-store identity is shared: MinIO's root user
# and pgBackRest's repo1-s3-key are the same principal in that profile.
credential_source_key() {
  case "$1" in
    PGBACKREST_REPO1_S3_KEY) printf 'IBEX_OBJECTSTORE_ACCESS_KEY\n' ;;
    PGBACKREST_REPO1_S3_KEY_SECRET) printf 'IBEX_OBJECTSTORE_SECRET_KEY\n' ;;
    *) printf '%s\n' "$1" ;;
  esac
}

# v1_repository_profile_selected reports whether the selected Compose file is a
# profile that wires the repository credentials into its postgres service. The
# generated v1-single-node configuration is the one that does; the dev and test
# stacks mention none of the three names.
v1_repository_profile_selected() {
  local compose_file="$1"
  [[ -f "$compose_file" ]] || return 1
  grep -q 'PGBACKREST_REPO1_CIPHER_PASS' "$compose_file"
}

# load_v1_repository_credentials fills the three credentials from the profile
# dotenv (0600) when the v1 configuration is selected and they are not already
# in this script's environment.
#
# The failure this guards is a *direct* invocation with COMPOSE_FILE pointing at
# the v1 file. Compose loads the credentials from the dotenv beside that file, so
# the restore container would receive them, but this script sees none: the
# credential list came out empty, the delivery probe was skipped entirely, and
# Postgres was stopped for a restore that then could not authenticate against an
# encrypted repository.
#
# The dotenv is a *fallback for a missing value*, never a precondition. Checking
# for the file before looking at the environment refused a legitimate recovery
# path: an operator who supplies all three values through the environment and has
# no profile .env available (a recovery host, a break-glass shell, a restore of
# the secrets backup) was rejected before the values it already held were
# considered. The file is therefore required — and read — only when a credential
# actually has to be loaded from it.
#
# The dotenv is read with the repository's Compose-dotenv reader, never sourced:
# sourcing would execute the file as shell code and would not decode it the way
# Compose does. Values land in shell variables only; nothing is exported,
# printed, or placed on a command line.
load_v1_repository_credentials() {
  local env_file="${IBEX_V1_ENV:-$ROOT/infra/compose/v1-single-node/.env}"
  local var key value
  local -a missing=()
  for var in "${CRED_NAMES[@]}"; do
    if [[ -n "${!var:-}" ]]; then
      continue
    fi
    key="$(credential_source_key "$var")"
    if [[ ! -f "$env_file" ]]; then
      echo "[restore] FAILED: $var is not in the environment and $env_file is missing, so it cannot be loaded; nothing has been stopped" >&2
      echo "[restore] export the three PGBACKREST_REPO1_* values, or run 'make v1-restore' (or 'make v1-pitr TARGET=...'), which loads them from the profile .env first" >&2
      return 1
    fi
    if ! value="$(python3 "$ROOT/infra/scripts/lib/dotenv.py" "$key" <"$env_file")"; then
      echo "[restore] FAILED: could not read $key from $env_file; nothing has been stopped" >&2
      return 1
    fi
    if [[ -z "$value" ]]; then
      missing+=("$var (from $key)")
      continue
    fi
    printf -v "$var" '%s' "$value"
  done
  if (( ${#missing[@]} )); then
    echo "[restore] FAILED: the v1 profile is in use but these repository credentials are empty in $env_file: ${missing[*]}" >&2
    echo "[restore] run 'make v1-restore' (or 'make v1-pitr TARGET=...'), which loads them from the profile .env first" >&2
    return 1
  fi
  return 0
}

# Require the credentials the selected configuration implies before the first
# destructive step: before the credential file is written and long before
# Postgres is stopped, so a refusal leaves the database running.
if v1_repository_profile_selected "$COMPOSE_FILE"; then
  if ! load_v1_repository_credentials; then
    pitr_blocked "the v1 profile repository credentials could not be loaded (see the message above)"
    exit 1
  fi
fi

run_args=()
cred_vars=()
if [[ -n "$RESTORE_USER" ]]; then
  run_args+=(--user "$RESTORE_USER")
fi
for var in "${CRED_NAMES[@]}"; do
  if [[ -n "${!var:-}" ]]; then
    cred_vars+=("$var")
  fi
done

CRED_ENV_FILE=""
cleanup_cred_env_file() {
  if [[ -n "$CRED_ENV_FILE" ]]; then
    rm -f -- "$CRED_ENV_FILE"
    CRED_ENV_FILE=""
  fi
}

# digest_of prints the SHA-256 of one value. The value reaches sha256sum through
# a pipe, never through argv, so it cannot appear in `ps` or in the process
# table.
digest_of() {
  printf '%s' "$1" | sha256sum | awk '{print $1}'
}

# write_credential_env_file renders one KEY=value line per credential into a
# 0600 file, followed by one SHA-256 digest line per credential computed from the
# in-memory value (never from the file, which is what may be short).
#
# Every write is checked individually. This function is called from a negated
# condition (`if ! write_credential_env_file`), and bash suspends `set -e` inside
# a function invoked that way, so an unchecked `printf ... >>file` that failed on
# a full filesystem used to fall through to the trailing `chmod` and an
# unconditional `return 0`. A truncated last value is still non-empty, so the
# probe passed, Postgres was stopped, and pgBackRest then failed to authenticate
# with the database already down. Each write therefore reports its own failure,
# and the function returns success only after every write and the final mode
# check succeeded.
write_credential_env_file() {
  local var value digest
  (( ${#cred_vars[@]} )) || return 0
  if ! CRED_ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/ibex-pgbackrest-credentials.XXXXXX")"; then
    CRED_ENV_FILE=""
    echo "[restore] FAILED: could not create a temporary credential file in ${TMPDIR:-/tmp}; nothing has been stopped" >&2
    return 1
  fi
  if ! chmod 0600 "$CRED_ENV_FILE"; then
    echo "[restore] FAILED: could not set mode 0600 on $CRED_ENV_FILE; nothing has been stopped" >&2
    return 1
  fi
  for var in "${cred_vars[@]}"; do
    value="${!var}"
    if [[ -z "$value" ]]; then
      echo "[restore] refusing: $var is empty" >&2
      return 1
    fi
    if [[ "$value" =~ ^[[:space:]]|[[:space:]]$ || "$value" == *$'\n'* ]]; then
      echo "[restore] refusing: $var has leading or trailing whitespace, or contains a newline, which --env-file cannot carry; fix the value in the profile .env" >&2
      return 1
    fi
    digest="$(digest_of "$value")"
    if [[ -z "$digest" ]]; then
      echo "[restore] FAILED: sha256sum produced no digest for $var, so the delivery probe could not verify it; nothing has been stopped" >&2
      return 1
    fi
    if ! printf '%s=%s\n' "$var" "$value" >>"$CRED_ENV_FILE"; then
      echo "[restore] FAILED: could not write $var to the credential file (write error or short write); nothing has been stopped" >&2
      return 1
    fi
    if ! printf 'IBEX_CRED_SHA256_%s=%s\n' "$var" "$digest" >>"$CRED_ENV_FILE"; then
      echo "[restore] FAILED: could not write the $var digest to the credential file (write error or short write); nothing has been stopped" >&2
      return 1
    fi
  done
  # The final chmod is a real check, not decoration: it is the last thing that
  # can fail, and the function's exit status is its status. A prior write failure
  # has already returned 1, so this cannot mask one.
  if ! chmod 0600 "$CRED_ENV_FILE"; then
    echo "[restore] FAILED: could not reassert mode 0600 on $CRED_ENV_FILE; nothing has been stopped" >&2
    return 1
  fi
}

cred_file_args=()
if ! write_credential_env_file; then
  echo "[restore] FAILED: could not prepare the repository credentials; nothing has been stopped" >&2
  pitr_blocked "the repository credentials could not be written to a 0600 file; nothing has been stopped"
  exit 1
fi
if [[ -n "$CRED_ENV_FILE" ]]; then
  cred_file_args+=(--env-file "$CRED_ENV_FILE")
fi

# display_cred_args is what a *printed* command carries. The temporary file is
# gone by the time the operator pastes the command, so the printed form keeps
# `-e VAR`: the values have to come from the operator's own shell.
display_cred_args=()
for var in "${cred_vars[@]}"; do
  display_cred_args+=(-e "$var")
done

# probe_credential_delivery starts a throwaway container exactly the way the
# restore starts one and requires every credential to arrive *intact*: the
# SHA-256 the container computes over the value it received must equal the digest
# written beside that value when the file was produced.
#
# A non-empty check is not enough. A short write leaves a truncated last value
# that is still non-empty, so the old probe passed and Postgres was stopped. The
# digest line is an independent channel: it is computed from the in-memory value
# and the container compares against it, so a value the engine truncated,
# mangled, or dropped fails here, before Postgres is stopped.
#
# The probe needs sha256sum inside the image, which the Debian-based postgres
# image carries (coreutils). A missing sha256sum is refused explicitly rather
# than surfacing as a misleading digest mismatch.
probe_credential_delivery() {
  local image="$1" var script
  (( ${#cred_vars[@]} )) || return 0
  script="command -v sha256sum >/dev/null 2>&1 || { echo 'sha256sum is missing from the image, so credential delivery cannot be verified' >&2; exit 1; }; "
  for var in "${cred_vars[@]}"; do
    script+="want=\"\${IBEX_CRED_SHA256_${var}:?}\"; "
    script+="got=\"\$(printf '%s' \"\${${var}:-}\" | sha256sum)\"; got=\"\${got%% *}\"; "
    script+="[ \"\$got\" = \"\$want\" ] || { echo '${var} arrived truncated or altered' >&2; exit 1; }; "
  done
  if ! "${CLI[@]}" run --rm "${run_args[@]}" "${cred_file_args[@]}" --entrypoint sh "$image" -c "$script" >/dev/null; then
    echo "[restore] FAILED: the container engine did not deliver the repository credentials intact (${cred_vars[*]}) to a probe container started like the restore. Nothing has been stopped; Postgres is still running." >&2
    return 1
  fi
  echo "[restore] credential delivery verified: ${cred_vars[*]} arrive in a container with the expected values"
  return 0
}

# print_credential_load prints the loading step that belongs above the printed
# start command. That command forwards the credentials by name (`-e VAR`), which
# reads the value from the *operator's* shell: the environment that ran this
# script does not survive into that shell, and a bare shell forwards an empty
# value, so recovery then dies with
# "archive-get command requires option: repo1-cipher-pass".
#
# The script's own container runs do not use `-e` (see the credential block
# above); the printed form keeps it because a printed `--env-file` would name a
# file that no longer exists. If the engine is `sudo -n podman`, sudo resets the
# environment: write the values to a 0600 file and pass it with --env-file, or
# start the cluster without them — it runs with archive_mode=off and needs no
# repository access.
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
    source_key="$(credential_source_key "$var")"
    printf '  %s="$(ibex_env_value %s)"\n' "$var" "$source_key"
    printf '  : "${%s:?empty; check $ENV_FILE}"\n' "$var"
  done
  printf '  export %s\n\n' "${cred_vars[*]}"
}

# live_cluster_identity prints "<container>|<user>|<db>" for the running
# profile Postgres, or returns 1 when it is not running. Reading the identity
# from the container's own environment avoids a second source of truth for the
# superuser name.
live_cluster_identity() {
  local cid identity
  cid="$(compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null | head -n1 || true)"
  [[ -n "$cid" ]] || return 1
  identity="$("${CLI[@]}" exec "$cid" sh -c 'printf "%s|%s\n" "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-postgres}"' 2>/dev/null || true)"
  [[ -n "$identity" ]] || return 1
  printf '%s|%s\n' "$cid" "$identity"
}

# measure_live_wal_archive records WAL archive freshness before anything is
# restored. A backup or a restore forces a WAL switch, so measuring it afterwards
# would always look fresh. Archiving is not what gates the RPO claim: the bound
# is the frontier the restore demonstrates, and these counters are diagnostics an
# operator reads beside it.
#
# What is recorded is the *measurement*, not a claim: the upload age, the
# cluster's archive_timeout and its wal_segment_size. The pg_wal older-segment
# count is deliberately not measured — retained-but-archived segments make it
# uninterpretable — so wal_archive_backlog is null in every report this script
# writes (see the note beside PITR_WAL_ARCHIVE_WAL_SEGMENT_SIZE).
measure_live_wal_archive() {
  local identity cid user db row archived last_us last_seg cur_seg last_failed
  local archive_timeout seg_bytes now_us
  [[ -n "$PITR_REPORT" ]] || return 0
  identity="$(live_cluster_identity || true)"
  if [[ "$identity" != *"|"*"|"* ]]; then
    echo "[restore] live cluster not reachable; WAL archive freshness unmeasured"
    return 0
  fi
  cid="${identity%%|*}"
  user="${identity#*|}"
  user="${user%%|*}"
  db="${identity##*|}"
  # last_archived_time is when an upload *completed*, so it is not an RPO on its
  # own: a commit lands in WAL immediately and reaches the archive within
  # archive_timeout of its segment being switched, plus that segment's upload
  # latency. Microseconds keep the age exact; whole seconds would round it.
  row="$("${CLI[@]}" exec "$cid" psql -U "$user" -d "$db" -tAc \
    "SELECT archived_count || '|' || COALESCE((EXTRACT(EPOCH FROM last_archived_time) * 1000000)::bigint, -1) || '|' || COALESCE(last_archived_wal, '') || '|' || pg_walfile_name(pg_current_wal_lsn()) || '|' || CASE WHEN last_failed_time IS NOT NULL AND (last_archived_time IS NULL OR last_failed_time > last_archived_time) THEN 'true' ELSE 'false' END || '|' || COALESCE((EXTRACT(EPOCH FROM current_setting('archive_timeout')::interval))::bigint, -1) FROM pg_stat_archiver" \
    2>/dev/null | tr -d '\r' | tail -n1 || true)"
  # An empty row is "unmeasured", not a reason to abort: `read` returns 1 at
  # EOF, so the failure is swallowed here and handled by the checks below.
  IFS='|' read -r archived last_us last_seg cur_seg last_failed archive_timeout <<<"$row" || true
  # '' or a non-digit means the count is unusable, so RPO stays unmeasured. An
  # all-digit value is the valid case and is handled below, so the default arm
  # is a deliberate no-op rather than a silent acceptance.
  case "$archived" in
    '' | *[!0-9]*) return 0 ;;
    *) : ;;
  esac
  case "$last_us" in
    '' | *[!0-9-]*) return 0 ;;
    *) : ;;
  esac
  if (( archived == 0 || last_us <= 0 )); then
    echo "[restore] WAL archiving has archived no segment (archived_count=$archived) — RPO unmeasurable"
    return 0
  fi
  case "$archive_timeout" in
    '' | *[!0-9]*) archive_timeout="" ;;
    *) : ;;
  esac
  # The segment size stays: it sets how many segment files one WAL log id holds,
  # so an operator reading the archived/current names has the arithmetic.
  seg_bytes="$("${CLI[@]}" exec "$cid" psql -U "$user" -d "$db" -tAc \
    "SELECT pg_size_bytes(current_setting('wal_segment_size'))" \
    2>/dev/null | tr -d '\r' | tail -n1 || true)"
  case "$seg_bytes" in
    '' | *[!0-9]*) seg_bytes="" ;;
    *) : ;;
  esac
  now_us="$(date +%s%6N)"
  PITR_WAL_ARCHIVE_OK=true
  PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC=$(( (now_us - last_us) / 1000000 ))
  if (( PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC < 0 )); then
    PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC=0
  fi
  PITR_WAL_ARCHIVE_TIMEOUT_SEC="$archive_timeout"
  PITR_WAL_ARCHIVE_WAL_SEGMENT_SIZE="$seg_bytes"
  PITR_WAL_ARCHIVE_LAST_SEGMENT="$last_seg"
  PITR_WAL_ARCHIVE_CURRENT_SEGMENT="$cur_seg"
  PITR_WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE="$last_failed"
  echo "[restore] wal_archive_ok=true newest_archived_age_sec=$PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC archive_timeout_sec=${archive_timeout:-unknown} wal_segment_size_bytes=${seg_bytes:-unknown} last_archived_wal=${last_seg:-unknown} current_wal=${cur_seg:-unknown} failed_since_archive=${last_failed:-unknown}"
}

# recovery_identity prints "<user>|<db>" for a restored cluster.
#
# The live primary is the convenient source, but it is exactly what is missing
# during a real recovery: deriving the identity from a running container made
# every offline recovery connect as `postgres` against a cluster bootstrapped
# with `ibex`, so a valid restore failed verification after 120 s. Compose
# metadata for the selected profile answers the same question with nothing
# running, and the two overrides cover a host or break-glass restore.
recovery_identity() {
  local identity user db from_compose
  identity="$(live_cluster_identity || true)"
  if [[ "$identity" == *"|"*"|"* ]]; then
    user="${identity#*|}"
    user="${user%%|*}"
    db="${identity##*|}"
    printf '%s|%s\n' "$user" "$db"
    return 0
  fi
  if [[ -n "${PGBACKREST_RECOVERY_USER:-}" || -n "${PGBACKREST_RECOVERY_DB:-}" ]]; then
    printf '%s|%s\n' "${PGBACKREST_RECOVERY_USER:-postgres}" "${PGBACKREST_RECOVERY_DB:-postgres}"
    return 0
  fi
  from_compose="$(
    compose -f "$COMPOSE_FILE" config --format json 2>/dev/null | python3 -c '
import json, sys
cfg = json.load(sys.stdin)
svc = (cfg.get("services") or {}).get("postgres") or {}
env = svc.get("environment") or {}
if isinstance(env, list):
    env = dict(item.split("=", 1) for item in env if "=" in item)
print((env.get("POSTGRES_USER") or "postgres") + "|" + (env.get("POSTGRES_DB") or "postgres"))
' 2>/dev/null
  )" || true
  if [[ "$from_compose" == *"|"* ]]; then
    printf '%s\n' "$from_compose"
    return 0
  fi
  printf 'postgres|postgres\n'
}

# record_replay_fact records the last transaction the restored cluster replayed.
# It runs for *every* successful restore, targeted or not: the instant is the
# frontier an RPO upper bound is derived from, so an untargeted run needs it as
# much as a targeted one. It returns 1 when the value is unusable, and leaves the
# field empty — "not measured" must stay distinguishable from "measured as now".
record_replay_fact() {
  local replay_us="$1"
  case "$replay_us" in
    '' | *[!0-9-]*) return 1 ;;
    *) : ;;
  esac
  (( replay_us >= 0 )) || return 1
  PITR_RECOVERY_REPLAY_TIMESTAMP="$(format_epoch_micros "$replay_us")"
  return 0
}

# compare_recovery_target compares that fact with the requested target in integer
# microseconds. It runs only when a target was requested, and only on a value
# record_replay_fact accepted, so the comparison exists once and cannot drift
# between branches.
#
# An unreadable or absent replay value leaves PITR_RECOVERY_TARGET_REACHED empty,
# and the callers treat anything other than "true" as unproven: "not measured" is
# not "not missed".
compare_recovery_target() {
  local replay_us="$1"
  [[ -n "$iso_target" ]] || return 0
  if [[ -z "$target_micros" ]]; then
    PITR_RECOVERY_TARGET_REACHED=false
    echo "[restore] ERROR: the recovery target has no epoch value; target not proven" >&2
    return 0
  fi
  if (( replay_us <= target_micros )); then
    PITR_RECOVERY_TARGET_REACHED=true
    echo "[restore] recovery target reached: replay=$PITR_RECOVERY_REPLAY_TIMESTAMP target=$iso_target"
  else
    PITR_RECOVERY_TARGET_REACHED=false
    echo "[restore] ERROR: recovery replayed past the target (replay=$PITR_RECOVERY_REPLAY_TIMESTAMP target=$iso_target)" >&2
  fi
}

# record_recovery_facts is what every branch that verifies a restored cluster
# calls: record the replay instant, then grade the target against it when one was
# asked for.
record_recovery_facts() {
  record_replay_fact "$1" || return 0
  compare_recovery_target "$1"
}

# record_cluster_facts reads the recovery point and the data size back from a
# running restored cluster. "Reached the target" is a fact only when the
# cluster's own last replayed transaction says so.
record_cluster_facts() {
  local container="$1" identity user db row replay
  identity="$(recovery_identity || true)"
  user="${identity%%|*}"
  db="${identity#*|}"
  [[ -n "$user" ]] || user=postgres
  [[ -n "$db" ]] || db=postgres
  row="$("${CLI[@]}" exec "$container" psql -U "$user" -d "$db" -tAc \
    "SELECT COALESCE((EXTRACT(EPOCH FROM pg_last_xact_replay_timestamp()) * 1000000)::bigint, -1) || '|' || pg_database_size(current_database())" \
    2>/dev/null | tr -d '\r' | tail -n1 || true)"
  if [[ "$row" == *"|"* ]]; then
    replay="${row%%|*}"
    PITR_CLUSTER_DATA_BYTES="${row##*|}"
    # Clear the byte count when it is empty or non-numeric. An all-digit value is
    # the valid case and passes through unchanged, so the default is a no-op.
    case "$PITR_CLUSTER_DATA_BYTES" in
      '' | *[!0-9]*) PITR_CLUSTER_DATA_BYTES="" ;;
      *) : ;;
    esac
    # The replay epoch may legitimately be negative (-1 means "no replayed
    # transaction yet"), so the pattern also allows '-'.
    case "$replay" in
      '' | *[!0-9-]*) replay="" ;;
      *) : ;;
    esac
    record_recovery_facts "$replay"
  fi
  PITR_RESTORED_ORGS="$("${CLI[@]}" exec "$container" psql -U "$user" -d "$db" -tAc \
    "SELECT COUNT(*)::text FROM ibex_core.organizations" 2>/dev/null | tr -d "$PG_WS_TRIM" | tail -n1 || true)"
  # Empty or non-numeric clears the org count; an all-digit value is valid and
  # left as-is, so the default arm is a deliberate no-op.
  case "$PITR_RESTORED_ORGS" in
    '' | *[!0-9]*) PITR_RESTORED_ORGS="" ;;
    *) : ;;
  esac
  PITR_RESTORED_MEMORIES="$("${CLI[@]}" exec "$container" psql -U "$user" -d "$db" -tAc \
    "SET app.is_service_account = 'true'; SELECT COUNT(*)::text FROM ibex_core.memories" \
    2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true)"
  echo "[restore] restored cluster bytes=${PITR_CLUSTER_DATA_BYTES:-unknown} orgs=${PITR_RESTORED_ORGS:-unknown} memories=${PITR_RESTORED_MEMORIES:-unknown}"
}

# start_pitr_verify_container starts the restored scratch cluster with archiving
# disabled — the same command the printed next step documents — so the recovery
# point can be read instead of asserted. It is removed on exit; the restored
# volume is left in place, stopped, as before.
start_pitr_verify_container() {
  local network="$1" identity user db ready=false
  PITR_VERIFY_CONTAINER="ibex-pitr-verify-$$"
  if ! "${CLI[@]}" run -d --name "$PITR_VERIFY_CONTAINER" "${run_args[@]}" "${cred_file_args[@]}" \
    --network "$network" \
    -v "${SCRATCH_VOLUME}:/var/lib/postgresql/data" \
    -v "${CONF}:${CONTAINER_CONF}:ro" \
    "$IMAGE" postgres -c archive_mode=off >/dev/null; then
    echo "[restore] FAILED: could not start the restored scratch cluster" >&2
    return 1
  fi
  identity="$(recovery_identity || true)"
  user="${identity%%|*}"
  db="${identity#*|}"
  [[ -n "$user" ]] || user=postgres
  [[ -n "$db" ]] || db=postgres
  for _ in $(seq 1 120); do
    if [[ "$("${CLI[@]}" exec "$PITR_VERIFY_CONTAINER" psql -U "$user" -d "$db" -tAc 'select pg_is_in_recovery()' 2>/dev/null | tr -d "$PG_WS_TRIM" || true)" == "f" ]]; then
      ready=true
      break
    fi
    sleep 1
  done
  if [[ "$ready" != "true" ]]; then
    # The server log is the only place that says why recovery stopped — a
    # target beyond the end of the archived WAL, a missing repository
    # credential, a corrupt segment. Print it instead of making the operator
    # reproduce the failure to find out.
    echo "[restore] FAILED: the restored scratch cluster did not leave recovery within 120s" >&2
    "${CLI[@]}" logs --tail 40 "$PITR_VERIFY_CONTAINER" >&2 || true
    return 1
  fi
  echo "[restore] scratch cluster verified: pg_is_in_recovery()=false"
  return 0
}

measure_live_wal_archive

if [[ -n "$SCRATCH_VOLUME" ]]; then
  # Drill path: restore beside the live cluster. Nothing is stopped, and the
  # live data directory is never mounted.
  if ! "${CLI[@]}" volume inspect "$SCRATCH_VOLUME" >/dev/null 2>&1; then
    echo "[restore] scratch volume $SCRATCH_VOLUME does not exist; create it first" >&2
    pitr_blocked "scratch volume $SCRATCH_VOLUME does not exist; create it first"
    exit 1
  fi
  if ! NETWORK="$(resolve_compose_network "$COMPOSE_FILE")"; then
    pitr_blocked "the Compose network for the restore container could not be resolved (no container, or no network on it)"
    exit 1
  fi
  echo "[restore] scratch restore volume=$SCRATCH_VOLUME network=$NETWORK image=$IMAGE"
  PITR_ATTEMPTED=true
  PITR_RESTORE_TARGET=scratch
  if ! "${CLI[@]}" run --rm "${run_args[@]}" "${cred_file_args[@]}" \
    --network "$NETWORK" \
    -v "${SCRATCH_VOLUME}:/var/lib/postgresql/data" \
    -v "${CONF}:${CONTAINER_CONF}:ro" \
    "$IMAGE" \
    pgbackrest --config="$CONTAINER_CONF" \
      --stanza="$STANZA" --pg1-path=/var/lib/postgresql/data "${restore_args[@]}" restore; then
    echo "[restore] FAILED: pgbackrest restore into $SCRATCH_VOLUME failed; the restored cluster is not verified" >&2
    exit 1
  fi
  echo "[restore] scratch restore ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # The restore returning 0 is not evidence that recovery stopped at the target.
  # Start the restored copy the way the printed step documents, read the last
  # replayed transaction, and only then record the run as a success.
  if ! start_pitr_verify_container "$NETWORK"; then
    cleanup_pitr_verify_container
    echo "[restore] FAILED: the restored cluster could not be verified; not reporting a successful PITR" >&2
    exit 1
  fi
  record_cluster_facts "$PITR_VERIFY_CONTAINER"
  cleanup_pitr_verify_container
  # Only an affirmative result is a proof. An empty value means psql failed, the
  # row was malformed, or no transaction had been replayed yet, and none of those
  # is a restore that stopped where it was asked to.
  if [[ -n "$iso_target" && "$PITR_RECOVERY_TARGET_REACHED" != "true" ]]; then
    pitr_failed "the restored cluster did not prove the requested target ($iso_target)"
    echo "[restore] FAILED: the restored cluster did not prove the requested target" >&2
    exit 1
  fi
  PITR_BACKUP_OK=true
  PITR_RESTORE_OK=true
  # The printed command names the connection the restore actually used, resolved
  # once here rather than twice inside the heredoc.
  NEXT_IDENTITY="$(recovery_identity)"
  NEXT_USER="${NEXT_IDENTITY%%|*}"
  NEXT_DB="${NEXT_IDENTITY#*|}"
  cat <<NEXT

The restored cluster is not running. Start it on the scratch volume, with
archiving disabled so the restored timeline cannot write into the live
repository, then verify the recovery point.

$(print_credential_load)
  ${CLI[*]} run -d --name ibex-pitr-scratch --network $NETWORK ${run_args[*]} ${display_cred_args[*]} \\
    -v $SCRATCH_VOLUME:/var/lib/postgresql/data \\
    -v $CONF:$CONTAINER_CONF:ro \\
    $IMAGE postgres -c archive_mode=off

  ${CLI[*]} exec ibex-pitr-scratch psql -U $NEXT_USER -d $NEXT_DB \\
    -c 'SELECT pg_is_in_recovery(), pg_last_xact_replay_timestamp()'
NEXT
  exit 0
fi

# compose_restore_available predicts the destructive branch below: the restore
# runs in a container only when Compose can see a postgres service to stop.
compose_restore_available() {
  command -v "${CLI[0]}" >/dev/null 2>&1 || return 1
  [[ -f "$COMPOSE_FILE" ]] || return 1
  [[ -n "$(compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null || true)" ]]
}

# Prove credential delivery *before* the first destructive action. This is the
# check that the `-e VAR` form could not make: under a rootful engine the
# container came up with empty values and the restore died after Postgres was
# stopped.
if compose_restore_available && ! probe_credential_delivery "$IMAGE"; then
  pitr_blocked "the container engine did not deliver the repository credentials intact to a probe container; nothing has been stopped"
  exit 1
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
# Record the quiesce instant only here: both stop attempts have returned and the
# refusal above has ruled out the unsafe run whose stop failed. Nothing new
# reaches the archive after the primary stops, so this instant freezes the
# frontier the RPO upper bound is measured from. An unsafe run records nothing,
# and therefore cannot claim a bound.
if [[ "$stopped" == "true" ]]; then
  PITR_WAL_ARCHIVE_QUIESCED_AT="$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)"
  echo "[restore] WAL archiving quiesced at $PITR_WAL_ARCHIVE_QUIESCED_AT (primary stopped)"
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
    in_recovery="$("${CLI[@]}" exec "$cid" sh -c 'psql -U "$POSTGRES_USER" -d postgres -tAc "select pg_is_in_recovery()"' 2>/dev/null | tr -d "$PG_WS_TRIM" || true)"
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

# record_host_cluster_facts reads the recovery point and the data size from a
# host cluster that was just verified. The IBEX database is used when the
# restored cluster has one: pg_database_size() of `postgres` measures the
# maintenance database, not the data that was restored, and reporting it would
# flatter the restore with a number that proves nothing.
record_host_cluster_facts() {
  local -a psql_cmd=("$@")
  local db=postgres row replay has_ibex
  # The first argument is the command, and everything after it is a connection
  # option. Passing the options alone is how this function once ran `-p` as a
  # command: every query failed silently, the target stayed unproven, and a
  # recovery that worked was reported as a missed target. A command may be a bare
  # name or a path; an option is never one.
  if [[ -z "${psql_cmd[0]:-}" || "${psql_cmd[0]}" == -* ]]; then
    echo "[restore] FAILED: record_host_cluster_facts needs the psql command as its first argument, got '${psql_cmd[0]:-<empty>}'" >&2
    return 1
  fi
  has_ibex="$("${psql_cmd[@]}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'ibex'" 2>/dev/null | tr -d "$PG_WS_TRIM" || true)"
  if [[ "$has_ibex" == "1" ]]; then
    db=ibex
  fi
  row="$("${psql_cmd[@]}" -d "$db" -tAc \
    "SELECT COALESCE((EXTRACT(EPOCH FROM pg_last_xact_replay_timestamp()) * 1000000)::bigint, -1) || '|' || pg_database_size(current_database())" \
    2>/dev/null | tr -d '\r' | tail -n1 || true)"
  if [[ "$row" == *"|"* ]]; then
    replay="${row%%|*}"
    PITR_CLUSTER_DATA_BYTES="${row##*|}"
    case "$PITR_CLUSTER_DATA_BYTES" in
      '' | *[!0-9]*) PITR_CLUSTER_DATA_BYTES="" ;;
      *) : ;;
    esac
    case "$replay" in
      '' | *[!0-9-]*) replay="" ;;
      *) : ;;
    esac
    record_recovery_facts "$replay"
  fi
  if [[ "$db" == "ibex" ]]; then
    PITR_RESTORED_ORGS="$("${psql_cmd[@]}" -d "$db" -tAc "SELECT COUNT(*)::text FROM ibex_core.organizations" 2>/dev/null | tr -d "$PG_WS_TRIM" | tail -n1 || true)"
    case "$PITR_RESTORED_ORGS" in
      '' | *[!0-9]*) PITR_RESTORED_ORGS="" ;;
      *) : ;;
    esac
    PITR_RESTORED_MEMORIES="$("${psql_cmd[@]}" -d "$db" -tAc "SET app.is_service_account = 'true'; SELECT COUNT(*)::text FROM ibex_core.memories" 2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true)"
  fi
  echo "[restore] restored cluster bytes=${PITR_CLUSTER_DATA_BYTES:-unknown} orgs=${PITR_RESTORED_ORGS:-unknown} memories=${PITR_RESTORED_MEMORIES:-unknown}"
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
  pg_port="$(sed -n '4p' "$pidfile" | tr -d "$PG_WS_TRIM")"
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
    in_recovery="$(psql "${psql_target[@]}" -d postgres -tAc 'select pg_is_in_recovery()' 2>/dev/null | tr -d "$PG_WS_TRIM" || true)"
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
  # The host branch used to stop here, so every targeted host restore reached
  # the same success state without anyone reading the replayed transaction. The
  # facts are read through the connection proven above: psql first, then the
  # options it was built from.
  if ! record_host_cluster_facts psql "${psql_target[@]}"; then
    echo "[restore] FAILED: the restored cluster's recovery facts could not be read" >&2
    return 1
  fi
  return 0
}

echo "[restore] stanza=$STANZA target=$TARGET conf=$CONF"
PITR_ATTEMPTED=true
# Both destructive sub-branches below restore over the real data directory — the
# Compose volume, or a host PGDATA — so this run records `host` whatever its
# environment class says.
PITR_RESTORE_TARGET=host
if [[ "$stopped_via_compose" == "true" && -n "$COMPOSE_VOLUME" ]]; then
  # Host pgbackrest cannot resolve the object store; run inside the compose
  # network.
  if ! NETWORK="$(resolve_compose_network "$COMPOSE_FILE")"; then
    pitr_failed "the Compose network for the restore container could not be resolved after Postgres was stopped"
    exit 1
  fi
  echo "[restore] running pgbackrest in compose network=$NETWORK image=$IMAGE"
  if ! "${CLI[@]}" run --rm "${run_args[@]}" "${cred_file_args[@]}" \
    --network "$NETWORK" \
    -v "${COMPOSE_VOLUME}:${TARGET}" \
    -v "${CONF}:${CONTAINER_CONF}:ro" \
    "$IMAGE" \
    pgbackrest --config="$CONTAINER_CONF" \
      --stanza="$STANZA" --pg1-path="$TARGET" "${destructive_restore_args[@]}" restore; then
    echo "[restore] FAILED: pgbackrest restore failed; the cluster is left stopped" >&2
    exit 1
  fi
  if ! verify_destructive_restore_compose; then
    exit 1
  fi
  RESTORED_CID="$(compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null | head -n1 || true)"
  if [[ -n "$RESTORED_CID" ]]; then
    record_cluster_facts "$RESTORED_CID"
  fi
  if [[ -n "$iso_target" && "$PITR_RECOVERY_TARGET_REACHED" != "true" ]]; then
    pitr_failed "the restored cluster did not prove the requested target ($iso_target)"
    echo "[restore] FAILED: the restored cluster did not prove the requested target" >&2
    exit 1
  fi
else
  if ! pgbackrest --config="$CONF" --stanza="$STANZA" --pg1-path="$TARGET" "${destructive_restore_args[@]}" restore; then
    echo "[restore] FAILED: pgbackrest restore failed; the cluster is left stopped" >&2
    exit 1
  fi
  if ! verify_destructive_restore_host; then
    exit 1
  fi
  if [[ -n "$iso_target" && "$PITR_RECOVERY_TARGET_REACHED" != "true" ]]; then
    pitr_failed "the restored cluster did not prove the requested target ($iso_target)"
    echo "[restore] FAILED: the restored cluster did not prove the requested target" >&2
    exit 1
  fi
fi
# A successful restore is also the proof that the backup it read was usable, so
# the report records backup_ok alongside restore_ok.
PITR_BACKUP_OK=true
PITR_RESTORE_OK=true
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
