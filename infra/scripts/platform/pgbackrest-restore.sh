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
PITR_WAL_ARCHIVE_OK=false
PITR_RPO_MEASURED=""
# Record the requested target immediately: a run blocked before the target is
# parsed must still say which recovery point was asked for.
PITR_TARGET_TIMESTAMP="${PGBACKREST_RESTORE_TARGET:-}"
PITR_RECOVERY_TARGET_REACHED=""
PITR_RECOVERY_REPLAY_TIMESTAMP=""
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

cleanup_pitr_verify_container() {
  if [[ -n "$PITR_VERIFY_CONTAINER" ]]; then
    "${CLI[@]}" rm -f "$PITR_VERIFY_CONTAINER" >/dev/null 2>&1 || true
    PITR_VERIFY_CONTAINER=""
  fi
}

emit_pitr_report() {
  [[ -n "$PITR_REPORT" ]] || return 0
  if [[ "$PITR_RESTORE_OK" != "true" && "$PITR_ATTEMPTED" != "true" && -z "$PITR_BLOCKED_BY" ]]; then
    echo "[restore] no PITR report written: the restore never started and no reason was recorded" >&2
    return 0
  fi
  PITR_REPORT="$PITR_REPORT" \
    PITR_STARTED_AT="$PITR_STARTED_AT" \
    PITR_ENVIRONMENT_CLASS="$(pitr_environment_class)" \
    PITR_MECHANISM="$PITR_MECHANISM" \
    PITR_BACKUP_OK="$PITR_BACKUP_OK" \
    PITR_RESTORE_OK="$PITR_RESTORE_OK" \
    PITR_WAL_ARCHIVE_OK="$PITR_WAL_ARCHIVE_OK" \
    PITR_RPO_MEASURED="$PITR_RPO_MEASURED" \
    PITR_TARGET_TIMESTAMP="$PITR_TARGET_TIMESTAMP" \
    PITR_RECOVERY_TARGET_REACHED="$PITR_RECOVERY_TARGET_REACHED" \
    PITR_RECOVERY_REPLAY_TIMESTAMP="$PITR_RECOVERY_REPLAY_TIMESTAMP" \
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
  emit_pitr_report || echo "[restore] WARNING: could not write the PITR report" >&2
  return "$status"
}
trap on_exit EXIT

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
# with optional milliseconds and optional `+HH[:MM]` offset, and rejects the
# `T` separator and `Z` suffix that an operator types. Validate the ISO8601
# form, then normalise it to the shape pgBackRest accepts so the documented
# `2026-11-14T09:01:00Z` input works instead of failing deep in the restore.
iso_target=""
target_epoch=""
if [[ -n "$RESTORE_TARGET" ]]; then
  if ! [[ "$RESTORE_TARGET" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[T\ ][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}(:?[0-9]{2})?)?$ ]]; then
    echo "[restore] PGBACKREST_RESTORE_TARGET is not an ISO8601 timestamp: $RESTORE_TARGET" >&2
    pitr_blocked "PGBACKREST_RESTORE_TARGET is not an ISO8601 timestamp: $RESTORE_TARGET"
    exit 2
  fi
  iso_target="$RESTORE_TARGET"
  PITR_TARGET_TIMESTAMP="$iso_target"
  target_epoch="$(date -u -d "$iso_target" +%s 2>/dev/null || true)"
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
# restored. RPO is the age of the newest recoverable segment, and a backup or a
# restore forces a WAL switch, so measuring it afterwards would always look
# fresh. When archiving is not proven the RPO field stays null and the report
# cannot claim an RPO pass.
measure_live_wal_archive() {
  local identity cid user db row archived last_epoch now
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
  row="$("${CLI[@]}" exec "$cid" psql -U "$user" -d "$db" -tAc \
    "SELECT archived_count || '|' || COALESCE(EXTRACT(EPOCH FROM last_archived_time)::bigint, -1) FROM pg_stat_archiver" \
    2>/dev/null | tr -d '\r' | tail -n1 || true)"
  if [[ "$row" != *"|"* ]]; then
    echo "[restore] WAL archive freshness unreadable (pg_stat_archiver)"
    return 0
  fi
  archived="${row%%|*}"
  last_epoch="${row##*|}"
  case "$archived" in '' | *[!0-9]*) return 0 ;; esac
  case "$last_epoch" in '' | *[!0-9]*) return 0 ;; esac
  if (( archived == 0 || last_epoch <= 0 )); then
    echo "[restore] WAL archiving has archived no segment (archived_count=$archived) — RPO unmeasurable"
    return 0
  fi
  now="$(date +%s)"
  PITR_WAL_ARCHIVE_OK=true
  PITR_RPO_MEASURED=$(( now - last_epoch ))
  if (( PITR_RPO_MEASURED < 0 )); then
    PITR_RPO_MEASURED=0
  fi
  echo "[restore] wal_archive_ok=true newest_archived_age_sec=$PITR_RPO_MEASURED"
}

# record_cluster_facts reads the recovery point and the data size back from a
# running restored cluster. "Reached the target" is a fact only when the
# cluster's own last replayed transaction says so.
record_cluster_facts() {
  local container="$1" identity user=postgres db=postgres row replay
  identity="$(live_cluster_identity || true)"
  if [[ "$identity" == *"|"*"|"* ]]; then
    user="${identity#*|}"
    user="${user%%|*}"
    db="${identity##*|}"
  fi
  [[ -n "$user" ]] || user=postgres
  [[ -n "$db" ]] || db=postgres
  row="$("${CLI[@]}" exec "$container" psql -U "$user" -d "$db" -tAc \
    "SELECT COALESCE(EXTRACT(EPOCH FROM pg_last_xact_replay_timestamp())::bigint, -1) || '|' || pg_database_size(current_database())" \
    2>/dev/null | tr -d '\r' | tail -n1 || true)"
  if [[ "$row" == *"|"* ]]; then
    replay="${row%%|*}"
    PITR_CLUSTER_DATA_BYTES="${row##*|}"
    case "$PITR_CLUSTER_DATA_BYTES" in '' | *[!0-9]*) PITR_CLUSTER_DATA_BYTES="" ;; esac
    case "$replay" in '' | *[!0-9-]*) replay="" ;; esac
    if [[ -n "$replay" ]] && (( replay >= 0 )); then
      PITR_RECOVERY_REPLAY_TIMESTAMP="$(date -u -d "@$replay" +%Y-%m-%dT%H:%M:%SZ)"
      if [[ -n "$target_epoch" ]]; then
        if (( replay <= target_epoch )); then
          PITR_RECOVERY_TARGET_REACHED=true
          echo "[restore] recovery target reached: replay=$PITR_RECOVERY_REPLAY_TIMESTAMP target=$iso_target"
        else
          PITR_RECOVERY_TARGET_REACHED=false
          echo "[restore] ERROR: recovery replayed past the target (replay=$PITR_RECOVERY_REPLAY_TIMESTAMP target=$iso_target)" >&2
        fi
      fi
    fi
  fi
  PITR_RESTORED_ORGS="$("${CLI[@]}" exec "$container" psql -U "$user" -d "$db" -tAc \
    "SELECT COUNT(*)::text FROM ibex_core.organizations" 2>/dev/null | tr -d '[:space:]' | tail -n1 || true)"
  case "$PITR_RESTORED_ORGS" in '' | *[!0-9]*) PITR_RESTORED_ORGS="" ;; esac
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
  local network="$1" identity user=postgres db=postgres ready=false
  PITR_VERIFY_CONTAINER="ibex-pitr-verify-$$"
  if ! "${CLI[@]}" run -d --name "$PITR_VERIFY_CONTAINER" "${run_args[@]}" "${cred_file_args[@]}" \
    --network "$network" \
    -v "${SCRATCH_VOLUME}:/var/lib/postgresql/data" \
    -v "${CONF}:${CONTAINER_CONF}:ro" \
    "$IMAGE" postgres -c archive_mode=off >/dev/null; then
    echo "[restore] FAILED: could not start the restored scratch cluster" >&2
    return 1
  fi
  identity="$(live_cluster_identity || true)"
  if [[ "$identity" == *"|"*"|"* ]]; then
    user="${identity#*|}"
    user="${user%%|*}"
    db="${identity##*|}"
  fi
  [[ -n "$user" ]] || user=postgres
  [[ -n "$db" ]] || db=postgres
  for _ in $(seq 1 120); do
    if [[ "$("${CLI[@]}" exec "$PITR_VERIFY_CONTAINER" psql -U "$user" -d "$db" -tAc 'select pg_is_in_recovery()' 2>/dev/null | tr -d '[:space:]' || true)" == "f" ]]; then
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
  NETWORK="$(resolve_compose_network "$COMPOSE_FILE")"
  echo "[restore] scratch restore volume=$SCRATCH_VOLUME network=$NETWORK image=$IMAGE"
  PITR_ATTEMPTED=true
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
  if [[ "$PITR_RECOVERY_TARGET_REACHED" == "false" ]]; then
    echo "[restore] FAILED: the restored cluster did not stop at the requested target" >&2
    exit 1
  fi
  PITR_BACKUP_OK=true
  PITR_RESTORE_OK=true
  cat <<NEXT

The restored cluster is not running. Start it on the scratch volume, with
archiving disabled so the restored timeline cannot write into the live
repository, then verify the recovery point.

$(print_credential_load)
  ${CLI[*]} run -d --name ibex-pitr-scratch --network $NETWORK ${run_args[*]} ${display_cred_args[*]} \\
    -v $SCRATCH_VOLUME:/var/lib/postgresql/data \\
    -v $CONF:$CONTAINER_CONF:ro \\
    $IMAGE postgres -c archive_mode=off

  ${CLI[*]} exec ibex-pitr-scratch psql -U ibex -d ibex \\
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
if compose_restore_available; then
  if ! probe_credential_delivery "$IMAGE"; then
    pitr_blocked "the container engine did not deliver the repository credentials intact to a probe container; nothing has been stopped"
    exit 1
  fi
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
PITR_ATTEMPTED=true
if [[ "$stopped_via_compose" == "true" && -n "$COMPOSE_VOLUME" ]]; then
  # Host pgbackrest cannot resolve the object store; run inside the compose
  # network.
  NETWORK="$(resolve_compose_network "$COMPOSE_FILE")"
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
  if [[ "$PITR_RECOVERY_TARGET_REACHED" == "false" ]]; then
    echo "[restore] FAILED: the restored cluster did not stop at the requested target" >&2
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
fi
# A successful restore is also the proof that the backup it read was usable, so
# the report records backup_ok alongside restore_ok.
PITR_BACKUP_OK=true
PITR_RESTORE_OK=true
echo "[restore] ok $(date -u +%Y-%m-%dT%H:%M:%SZ)"
