#!/usr/bin/env bash
# test-v1-backup-credentials.sh — regression tests for the v1 backup-repository
# credential chain.
#
# Seven properties are guarded here because they all protect the same secret:
#
#   1. gen-v1-secrets.sh never loses or silently replaces
#      PGBACKREST_REPO1_CIPHER_PASS. That passphrase is the only key to every
#      object in the repository: a regenerated one leaves the repository intact
#      but unreadable, and the operator finds out at restore time.
#   2. A retained passphrase is written back with the quoting and escaping the
#      repository's dotenv reader decodes, so a value containing a space or `#`
#      is not truncated by the next --force.
#   3. pgbackrest-restore.sh delivers the repository credentials to its
#      container in a way that survives a rootful `sudo -n podman` engine, and
#      proves delivery *intact* before it stops Postgres.
#   4. A credential write that fails part way (a full filesystem, a short write)
#      aborts the restore instead of leaving a truncated value that still looks
#      non-empty.
#   5. A direct invocation that selects the v1 profile refuses to stop Postgres
#      when it has no credentials, instead of collecting an empty credential
#      list and skipping the delivery probe.
#   6. The profile dotenv is a fallback for a missing value, not a precondition:
#      an invocation that already holds all three credentials in its environment
#      proceeds when no dotenv exists at all, and still proves delivery before
#      Postgres is stopped.
#   7. Every escape the repository's dotenv reader decodes is emitted on a
#      rewrite, including the carriage return that would otherwise split the
#      retained passphrase across two lines.
#   8. The Redis password is the directive of a generated config file the
#      profile mounts, and the compose file carries neither `--requirepass` nor
#      a healthcheck `-a <value>`: the secret must never be a container
#      command-line argument that `podman inspect` and /proc print.
#
# Every path is redirected: IBEX_V1_ENV_FILE, IBEX_V1_SECRETS_DIR,
# IBEX_V1_CERTS_DIR and IBEX_V1_PGBACKREST_CONF keep the generator out of the
# profile's real files, and a stub container engine stands in for docker/podman.
# No credential is printed; assertions compare values and report only the case
# name.
#
# Run directly: bash infra/scripts/test-v1-backup-credentials.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GEN="$ROOT_DIR/infra/scripts/gen-v1-secrets.sh"
RESTORE="$ROOT_DIR/infra/scripts/platform/pgbackrest-restore.sh"
DOTENV="$ROOT_DIR/infra/scripts/lib/dotenv.py"
COMPOSE="$ROOT_DIR/infra/compose/v1-single-node/compose.yml"

PASSED=0
pass() {
  PASSED=$((PASSED + 1))
  echo "PASS: $*"
}
fail() {
  echo "FAIL: $*" >&2
  exit 1
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ibex-v1-cred-tests.XXXXXX")"
cleanup() {
  chmod -R u+rwX "$WORK" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# --- generator harness -----------------------------------------------------

# gen_env points the generator at one throwaway directory. The bootstrap
# directory is the one path the generator still resolves in the repository; it
# is only created and chmod 0700, and the generator writes nothing into it.
gen_env() {
  local dir="$1"
  mkdir -p "$dir/env"
  IBEX_V1_ENV_FILE="$dir/env/.env"
  IBEX_V1_SECRETS_DIR="$dir/secrets"
  IBEX_V1_CERTS_DIR="$dir/certs"
  IBEX_V1_PGBACKREST_CONF="$dir/pgbackrest.conf"
  export IBEX_V1_ENV_FILE IBEX_V1_SECRETS_DIR IBEX_V1_CERTS_DIR IBEX_V1_PGBACKREST_CONF
}

env_read() {
  python3 "$DOTENV" "$1" <"$IBEX_V1_ENV_FILE"
}

env_sha() {
  sha256sum "$IBEX_V1_ENV_FILE" | awk '{print $1}'
}

# seed_env writes a .env holding only the repository passphrase, which is the
# state an existing installation is in when the generator is rerun.
seed_env() {
  printf 'PGBACKREST_REPO1_CIPHER_PASS=%s\n' "$1" >"$IBEX_V1_ENV_FILE"
  chmod 0600 "$IBEX_V1_ENV_FILE"
}

new_cipher() {
  openssl rand -hex 32
}

# --- case 1: fresh install -------------------------------------------------

dir="$WORK/fresh"
gen_env "$dir"
if ! bash "$GEN" >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "fresh install: generator exited non-zero"
fi
cipher="$(env_read PGBACKREST_REPO1_CIPHER_PASS)"
[[ "$cipher" =~ ^[0-9a-f]{64}$ ]] || fail "fresh install: no 64-hex repository passphrase was generated"
[[ "$(stat -c %a "$IBEX_V1_ENV_FILE")" == "600" ]] || fail "fresh install: .env is not mode 600"
pass "fresh install generates a repository passphrase"

# --- case 2: --force preserves the existing passphrase ---------------------

dir="$WORK/force"
gen_env "$dir"
cipher="$(new_cipher)"
seed_env "$cipher"
if ! bash "$GEN" --force >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "--force: generator exited non-zero"
fi
[[ "$(env_read PGBACKREST_REPO1_CIPHER_PASS)" == "$cipher" ]] \
  || fail "--force: the existing PGBACKREST_REPO1_CIPHER_PASS was not preserved"
grep -q '^POSTGRES_USER=ibex' "$IBEX_V1_ENV_FILE" \
  || fail "--force: .env was not rewritten from the template"
if [[ -n "$(find "$dir/env" -maxdepth 1 -name '.env.new.*' -print -quit)" ]]; then
  fail "--force: a staged .env temporary file was left behind"
fi
pass "--force keeps the existing repository passphrase"

# --- case 2b: the Redis password is a config directive, not an argv flag ---
#
# `command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}"]` put the
# password in Config.Cmd: `podman inspect` printed it and /proc/1/cmdline
# exposed it to every process in the container. The password is now the
# `requirepass` directive of a generated file the profile mounts, and the
# healthcheck authenticates through REDISCLI_AUTH instead of `-a <value>`.

dir="$WORK/redis"
gen_env "$dir"
if ! bash "$GEN" >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "redis config: generator exited non-zero"
fi
redis_conf="$IBEX_V1_SECRETS_DIR/redis.conf"
[[ -f "$redis_conf" ]] || fail "redis config: secrets/redis.conf was not generated"
[[ "$(stat -c %a "$redis_conf")" == "444" ]] \
  || fail "redis config: the container copy is not mode 444 like every other secret"
redis_password="$(env_read REDIS_PASSWORD)"
[[ -n "$redis_password" ]] || fail "redis config: no REDIS_PASSWORD was generated"
[[ "$(grep -c '^requirepass ' "$redis_conf")" == "1" ]] \
  || fail "redis config: expected exactly one requirepass directive"
[[ "$(sed -n 's/^requirepass //p' "$redis_conf")" == "$redis_password" ]] \
  || fail "redis config: the directive does not carry the .env password"
if grep -qF -- "$redis_password" "$dir/out.log"; then
  fail "redis config: the generator printed the password"
fi
# Comment lines are excluded: this file's own explanation names the flags it
# forbids, and the check is about the directives Compose executes.
if grep -v '^[[:space:]]*#' "$COMPOSE" | grep -q -- '--requirepass'; then
  fail "redis config: the compose command line still carries --requirepass"
fi
grep -q 'REDISCLI_AUTH' "$COMPOSE" \
  || fail "redis config: the healthcheck has no REDISCLI_AUTH environment"
if grep -v '^[[:space:]]*#' "$COMPOSE" | grep -q -- 'redis-cli --no-auth-warning -a'; then
  fail "redis config: the healthcheck still passes the password with -a"
fi
grep -q 'redis.conf:' "$COMPOSE" \
  || fail "redis config: compose does not declare the redis.conf secret"
pass "the Redis password is a mounted config directive and never an argv flag"

# --- case 3: explicit rotation without the override is refused -------------

dir="$WORK/rotate"
gen_env "$dir"
cipher="$(new_cipher)"
seed_env "$cipher"
before="$(env_sha)"
if bash "$GEN" --rotate-pgbackrest-cipher >"$dir/out.log" 2>&1; then
  fail "--rotate-pgbackrest-cipher: expected a refusal, generator succeeded"
fi
[[ "$before" == "$(env_sha)" ]] || fail "--rotate-pgbackrest-cipher: .env changed after a refusal"
grep -q 'refusing to rotate PGBACKREST_REPO1_CIPHER_PASS' "$dir/out.log" \
  || fail "--rotate-pgbackrest-cipher: refusal message missing"
pass "explicit rotation without the override is refused and leaves .env byte-identical"

# --- case 4: an unreadable .env aborts before anything is rewritten --------

if [[ "$(id -u)" -eq 0 ]]; then
  echo "SKIP: write-only .env case (running as root, which bypasses file modes)"
else
  dir="$WORK/unreadable"
  gen_env "$dir"
  cipher="$(new_cipher)"
  seed_env "$cipher"
  before="$(env_sha)"
  # Write-only, not mode 000: the defect is a .env that is writable (so a
  # rewrite succeeds) but unreadable (so the passphrase cannot be read back).
  chmod 0200 "$IBEX_V1_ENV_FILE"
  if bash "$GEN" --force >"$dir/out.log" 2>&1; then
    chmod 0600 "$IBEX_V1_ENV_FILE"
    fail "unreadable .env: generator succeeded instead of aborting"
  fi
  chmod 0600 "$IBEX_V1_ENV_FILE"
  [[ "$before" == "$(env_sha)" ]] || fail "unreadable .env: the file was overwritten"
  grep -q 'cannot read' "$dir/out.log" || fail "unreadable .env: abort message missing"
  pass "an unreadable .env aborts without overwriting the file"
fi

# --- restore harness -------------------------------------------------------

# write_stub renders a container engine that records its argv (never a value)
# and, for `run`, records whether --env-file points at a live 0600 file with
# the three repository keys.
write_stub() {
  cat >"$1" <<'STUB'
#!/usr/bin/env bash
set -u
log() { printf '%s\n' "$*" >>"$STUB_LOG"; }
# digest reads the value from the environment: a secret never reaches argv.
digest() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }

# truncate_last_value emulates an engine that could not carry the last value
# whole (a short write, a mangled line): the last credential loses half of its
# value and keeps a non-empty prefix.
truncate_last_value() {
  local file="$1" i keypart valuepart
  local -a lines=()
  mapfile -t lines <"$file"
  for ((i = ${#lines[@]} - 1; i >= 0; i--)); do
    if [[ "${lines[i]}" == PGBACKREST_REPO1_*=* ]]; then
      keypart="${lines[i]%%=*}"
      valuepart="${lines[i]#*=}"
      lines[i]="$keypart=${valuepart:0:${#valuepart}/2}"
      break
    fi
  done
  printf '%s\n' "${lines[@]}" >"$file"
}

first="${1:-}"
[[ -n "$first" ]] && shift
case "$first" in
  volume)
    log "VOLUME $*"
    exit 0
    ;;
  inspect)
    log "INSPECT $*"
    printf 'testnet\n'
    exit 0
    ;;
  compose)
    log "COMPOSE $*"
    case " $* " in
      *" ps "*) printf 'stubcid\n' ;;
    esac
    exit 0
    ;;
  exec)
    log "EXEC $*"
    # The post-restore check asks the cluster for pg_is_in_recovery().
    printf 'f\n'
    exit 0
    ;;
  run)
    log "RUN $*"
    envfile=""
    script=""
    previous=""
    for arg in "$@"; do
      if [[ "$previous" == "--env-file" ]]; then
        envfile="$arg"
      fi
      if [[ "$previous" == "-c" ]]; then
        script="$arg"
      fi
      previous="$arg"
    done
    if [[ -n "$envfile" ]]; then
      {
        printf 'ENVFILE_PATH=%s\n' "$envfile"
        printf 'ENVFILE_EXISTS=%s\n' "$([[ -f "$envfile" ]] && printf yes || printf no)"
        printf 'ENVFILE_MODE=%s\n' "$(stat -c %a "$envfile" 2>/dev/null || printf none)"
        printf 'ENVFILE_KEYS=%s\n' "$(grep -c '^PGBACKREST_REPO1_' "$envfile" 2>/dev/null || printf 0)"
        printf 'ENVFILE_DIGESTS=%s\n' "$(grep -c '^IBEX_CRED_SHA256_PGBACKREST_REPO1_' "$envfile" 2>/dev/null || printf 0)"
        printf 'ENVFILE_LINES=%s\n' "$(grep -c . "$envfile" 2>/dev/null || printf 0)"
      } >>"$STUB_ENV_REPORT"
    fi
    if [[ "${STUB_RUN_RESULT:-0}" != "0" ]]; then
      exit "$STUB_RUN_RESULT"
    fi
    # Emulate the probe container: the engine loads --env-file into the
    # container environment and runs the probe script inside it. STUB_TRUNCATE_ENV
    # makes the engine hand over a truncated value, which is what a short write or
    # a mangling engine would do.
    if [[ -n "$script" && -n "$envfile" && -f "$envfile" ]]; then
      if [[ -n "${STUB_TRUNCATE_ENV:-}" ]]; then
        truncate_last_value "$envfile"
      fi
      while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        export "$line" 2>/dev/null || true
      done <"$envfile"
      printf 'ENVFILE_CIPHER_SHA=%s\n' "$(digest "${PGBACKREST_REPO1_CIPHER_PASS:-}")" >>"$STUB_ENV_REPORT"
      sh -c "$script"
      exit $?
    fi
    exit 0
    ;;
esac
log "OTHER $first $*"
exit 0
STUB
  chmod 0755 "$1"
}

stub_report_value() {
  sed -n "s/^$1=//p" "$STUB_ENV_REPORT" | head -n1
}

# --- case 5: the container receives the credentials through --env-file -----

dir="$WORK/restore-scratch"
mkdir -p "$dir"
printf '[global]\nrepo1-type=s3\n' >"$dir/pgbackrest.conf"
printf 'services: {}\n' >"$dir/compose.yml"
write_stub "$dir/stub-engine"
STUB_LOG="$dir/calls.log"
STUB_ENV_REPORT="$dir/env-report.txt"
export STUB_LOG STUB_ENV_REPORT
: >"$STUB_LOG"
: >"$STUB_ENV_REPORT"

cipher="$(new_cipher)"
s3_key="$(new_cipher)"
s3_secret="$(new_cipher)"
# The exports are scoped to this subshell deliberately: each restore case runs
# the script with its own environment, and a value never reaches the parent
# shell, another case, or a command line.
# shellcheck disable=SC2030,SC2031
if ! (
  export PGBACKREST_REPO1_CIPHER_PASS="$cipher"
  export PGBACKREST_REPO1_S3_KEY="$s3_key"
  export PGBACKREST_REPO1_S3_KEY_SECRET="$s3_secret"
  export PGBACKREST_CONF="$dir/pgbackrest.conf"
  export PGBACKREST_STANZA=ibex-main
  export PGBACKREST_RESTORE_SCRATCH_VOLUME=stubvol
  export COMPOSE_FILE="$dir/compose.yml"
  export IBEX_CONTAINER_CLI="$dir/stub-engine"
  bash "$RESTORE"
) >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "restore scratch: exited non-zero"
fi
grep -q -- '--env-file' "$STUB_LOG" || fail "restore scratch: the container run did not use --env-file"
if grep -q -- ' -e PGBACKREST' "$STUB_LOG"; then
  fail "restore scratch: the container run still forwards credentials by name (-e)"
fi
envfile="$(stub_report_value ENVFILE_PATH)"
[[ -n "$envfile" ]] || fail "restore scratch: no --env-file path was recorded"
[[ "$(stub_report_value ENVFILE_EXISTS)" == "yes" ]] || fail "restore scratch: the credential file was absent during the run"
[[ "$(stub_report_value ENVFILE_MODE)" == "600" ]] || fail "restore scratch: the credential file was not mode 600"
[[ "$(stub_report_value ENVFILE_KEYS)" == "3" ]] || fail "restore scratch: the credential file did not carry all three keys"
[[ "$(stub_report_value ENVFILE_DIGESTS)" == "3" ]] || fail "restore scratch: the credential file did not carry all three digests"
[[ "$(stub_report_value ENVFILE_LINES)" == "6" ]] || fail "restore scratch: the credential file carried extra entries"
[[ ! -e "$envfile" ]] || fail "restore scratch: the credential file was not removed on exit"
for secret in "$cipher" "$s3_key" "$s3_secret"; do
  if grep -qF -- "$secret" "$dir/out.log"; then
    fail "restore scratch: a credential value appeared in the output"
  fi
done
pass "the restore container receives the credentials through a 0600 --env-file that is removed on exit"

# --- case 6: delivery is proven before Postgres is stopped -----------------

dir="$WORK/restore-gate"
mkdir -p "$dir"
printf '[global]\nrepo1-type=s3\n' >"$dir/pgbackrest.conf"
printf 'services: {}\n' >"$dir/compose.yml"
write_stub "$dir/stub-engine"
STUB_LOG="$dir/calls.log"
STUB_ENV_REPORT="$dir/env-report.txt"
export STUB_LOG STUB_ENV_REPORT
: >"$STUB_LOG"
: >"$STUB_ENV_REPORT"

cipher="$(new_cipher)"
# shellcheck disable=SC2030,SC2031
if (
  export PGBACKREST_REPO1_CIPHER_PASS="$cipher"
  export PGBACKREST_CONF="$dir/pgbackrest.conf"
  export PGBACKREST_STANZA=ibex-main
  export COMPOSE_FILE="$dir/compose.yml"
  export IBEX_CONTAINER_CLI="$dir/stub-engine"
  export STUB_RUN_RESULT=1
  bash "$RESTORE"
) >"$dir/out.log" 2>&1; then
  fail "delivery gate: the restore continued although the probe container failed"
fi
grep -q 'did not deliver the repository credentials' "$dir/out.log" \
  || fail "delivery gate: the failure message is missing"
grep -q -- '--entrypoint sh' "$STUB_LOG" || fail "delivery gate: the probe container was not started"
if grep -q ' stop ' "$STUB_LOG"; then
  fail "delivery gate: Postgres was stopped before credential delivery was proven"
fi
pass "a failed credential probe aborts before Postgres is stopped"

# --- case 7: a short credential write aborts before anything is stopped ----

# A full filesystem does not fail the first write: it writes a prefix and then
# errors, which used to leave a truncated last value that the non-empty probe
# accepted. RLIMIT_FSIZE reproduces that exactly, and ignoring SIGXFSZ turns the
# kernel's signal into the ordinary write error a full filesystem raises.
dir="$WORK/restore-short-write"
mkdir -p "$dir/tmp"
printf '[global]\nrepo1-type=s3\n' >"$dir/pgbackrest.conf"
printf 'services: {}\n' >"$dir/compose.yml"
write_stub "$dir/stub-engine"
STUB_LOG="$dir/calls.log"
STUB_ENV_REPORT="$dir/env-report.txt"
export STUB_LOG STUB_ENV_REPORT
: >"$STUB_LOG"
: >"$STUB_ENV_REPORT"

# 470-byte values put the third credential write across the 1 KiB limit, so the
# last value is the one that is cut in half.
long_value="$(printf 'k%.0s' {1..470})"
short_write_cipher="$(new_cipher)"
# shellcheck disable=SC2030,SC2031
if (
  trap '' XFSZ 2>/dev/null || true
  ulimit -f 1
  export TMPDIR="$dir/tmp"
  export PGBACKREST_REPO1_CIPHER_PASS="$short_write_cipher"
  export PGBACKREST_REPO1_S3_KEY="$long_value"
  export PGBACKREST_REPO1_S3_KEY_SECRET="$long_value"
  export PGBACKREST_CONF="$dir/pgbackrest.conf"
  export PGBACKREST_STANZA=ibex-main
  export COMPOSE_FILE="$dir/compose.yml"
  export IBEX_CONTAINER_CLI="$dir/stub-engine"
  bash "$RESTORE"
) >"$dir/out.log" 2>&1; then
  fail "short write: the restore continued although the last credential write failed"
fi
if grep -q ' stop ' "$STUB_LOG"; then
  fail "short write: Postgres was stopped after a truncated credential write"
fi
grep -q 'could not write PGBACKREST_REPO1_S3_KEY_SECRET to the credential file' "$dir/out.log" \
  || fail "short write: the failed write was not reported by name"
[[ ! -s "$STUB_LOG" ]] || fail "short write: the container engine was invoked before the write failure aborted the restore"
[[ -z "$(ls -A "$dir/tmp")" ]] || fail "short write: a truncated credential file was left behind"
pass "a short credential write aborts before the engine is invoked and before Postgres is stopped"

# --- case 8: a truncated value cannot pass the delivery probe --------------

dir="$WORK/restore-truncated"
mkdir -p "$dir"
printf '[global]\nrepo1-type=s3\n' >"$dir/pgbackrest.conf"
printf 'services: {}\n' >"$dir/compose.yml"
write_stub "$dir/stub-engine"
STUB_LOG="$dir/calls.log"
STUB_ENV_REPORT="$dir/env-report.txt"
export STUB_LOG STUB_ENV_REPORT
: >"$STUB_LOG"
: >"$STUB_ENV_REPORT"

cipher="$(new_cipher)"
s3_key="$(new_cipher)"
s3_secret="$(new_cipher)"
# shellcheck disable=SC2030,SC2031
if (
  export PGBACKREST_REPO1_CIPHER_PASS="$cipher"
  export PGBACKREST_REPO1_S3_KEY="$s3_key"
  export PGBACKREST_REPO1_S3_KEY_SECRET="$s3_secret"
  export PGBACKREST_CONF="$dir/pgbackrest.conf"
  export PGBACKREST_STANZA=ibex-main
  export COMPOSE_FILE="$dir/compose.yml"
  export IBEX_CONTAINER_CLI="$dir/stub-engine"
  export STUB_TRUNCATE_ENV=1
  bash "$RESTORE"
) >"$dir/out.log" 2>&1; then
  fail "truncated delivery: the restore continued although the container received a truncated value"
fi
grep -q 'did not deliver the repository credentials intact' "$dir/out.log" \
  || fail "truncated delivery: the integrity failure was not reported"
grep -q -- '--entrypoint sh' "$STUB_LOG" || fail "truncated delivery: the probe container was not started"
if grep -q ' stop ' "$STUB_LOG"; then
  fail "truncated delivery: Postgres was stopped although the delivered value was truncated"
fi
pass "a value truncated in transit fails the probe before Postgres is stopped"

# --- case 9: a retained passphrase with a space and a # survives --force ---

dir="$WORK/force-quoting"
gen_env "$dir"
# Single quotes are literal for the repository's reader, so the effective value
# is `fixture # suffix` and a bare rewrite would decode as `fixture`.
printf "PGBACKREST_REPO1_CIPHER_PASS='fixture # suffix'\n" >"$IBEX_V1_ENV_FILE"
chmod 0600 "$IBEX_V1_ENV_FILE"
before="$(env_read PGBACKREST_REPO1_CIPHER_PASS)"
[[ "$before" == 'fixture # suffix' ]] || fail "quoting: the fixture .env did not decode to the expected value"
if ! bash "$GEN" --force >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "quoting: generator exited non-zero"
fi
after="$(env_read PGBACKREST_REPO1_CIPHER_PASS)"
[[ "$after" == "$before" ]] \
  || fail "quoting: --force changed the value the repository's dotenv reader decodes"
grep -q '^PGBACKREST_REPO1_CIPHER_PASS="' "$IBEX_V1_ENV_FILE" \
  || fail "quoting: the retained passphrase was written back unquoted"
pass "--force preserves a passphrase containing a space and a # byte for byte"

# --- case 10: a direct v1 invocation without credentials refuses -----------

dir="$WORK/restore-no-credentials"
mkdir -p "$dir"
printf '[global]\nrepo1-type=s3\n' >"$dir/pgbackrest.conf"
write_stub "$dir/stub-engine"
STUB_LOG="$dir/calls.log"
STUB_ENV_REPORT="$dir/env-report.txt"
export STUB_LOG STUB_ENV_REPORT
: >"$STUB_LOG"
: >"$STUB_ENV_REPORT"

# COMPOSE_FILE selects the generated v1 profile, which loads the repository
# credentials from the dotenv beside it, but this shell exports none of them.
# shellcheck disable=SC2030,SC2031
if (
  unset PGBACKREST_REPO1_CIPHER_PASS PGBACKREST_REPO1_S3_KEY PGBACKREST_REPO1_S3_KEY_SECRET
  export PGBACKREST_CONF="$dir/pgbackrest.conf"
  export PGBACKREST_STANZA=ibex-main
  export COMPOSE_FILE="$ROOT_DIR/infra/compose/v1-single-node/compose.yml"
  export IBEX_V1_ENV="$dir/absent.env"
  export IBEX_CONTAINER_CLI="$dir/stub-engine"
  bash "$RESTORE"
) >"$dir/out.log" 2>&1; then
  fail "no credentials: the restore continued although the v1 profile was selected without credentials"
fi
grep -q 'make v1-restore' "$dir/out.log" \
  || fail "no credentials: the refusal did not point at the v1 wrapper"
[[ ! -s "$STUB_LOG" ]] \
  || fail "no credentials: the container engine was invoked before the credentials were validated"
pass "a direct v1 invocation without credentials refuses before the engine is asked to stop"

# --- case 11: the same invocation loads them from the profile dotenv -------

dir="$WORK/restore-v1-env"
mkdir -p "$dir"
printf '[global]\nrepo1-type=s3\n' >"$dir/pgbackrest.conf"
write_stub "$dir/stub-engine"
# The three credentials as the v1 profile stores them. The passphrase carries a
# space and a # so the loader has to decode the dotenv the way Compose does.
cat >"$dir/.env" <<'ENV'
IBEX_OBJECTSTORE_ACCESS_KEY=fixtureaccesskey
IBEX_OBJECTSTORE_SECRET_KEY=fixturesecretkey
PGBACKREST_REPO1_CIPHER_PASS='fixture # suffix'
ENV
chmod 0600 "$dir/.env"
STUB_LOG="$dir/calls.log"
STUB_ENV_REPORT="$dir/env-report.txt"
export STUB_LOG STUB_ENV_REPORT
: >"$STUB_LOG"
: >"$STUB_ENV_REPORT"

# shellcheck disable=SC2030,SC2031
if ! (
  unset PGBACKREST_REPO1_CIPHER_PASS PGBACKREST_REPO1_S3_KEY PGBACKREST_REPO1_S3_KEY_SECRET
  export PGBACKREST_CONF="$dir/pgbackrest.conf"
  export PGBACKREST_STANZA=ibex-main
  export PGBACKREST_COMPOSE_VOLUME=stubvol
  export COMPOSE_FILE="$ROOT_DIR/infra/compose/v1-single-node/compose.yml"
  export IBEX_V1_ENV="$dir/.env"
  export IBEX_CONTAINER_CLI="$dir/stub-engine"
  bash "$RESTORE"
) >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "v1 dotenv: the restore exited non-zero with credentials available in the profile .env"
fi
[[ "$(stub_report_value ENVFILE_KEYS)" == "3" ]] \
  || fail "v1 dotenv: the credential file did not carry all three credentials"
expected_cipher="$(python3 "$DOTENV" PGBACKREST_REPO1_CIPHER_PASS <"$dir/.env")"
expected_sha="$(printf '%s' "$expected_cipher" | sha256sum | awk '{print $1}')"
[[ "$(stub_report_value ENVFILE_CIPHER_SHA)" == "$expected_sha" ]] \
  || fail "v1 dotenv: the container did not receive the passphrase the profile .env holds"
probe_line="$(grep -n -- '--entrypoint sh' "$STUB_LOG" | head -n1 | cut -d: -f1)"
stop_line="$(grep -n -- ' stop postgres' "$STUB_LOG" | head -n1 | cut -d: -f1)"
[[ -n "$probe_line" && -n "$stop_line" && "$probe_line" -lt "$stop_line" ]] \
  || fail "v1 dotenv: Postgres was not stopped after credential delivery was proven"
if grep -qF -- "$expected_cipher" "$dir/out.log"; then
  fail "v1 dotenv: a credential value appeared in the output"
fi
pass "a direct v1 invocation loads the credentials from the profile .env and proves delivery before stopping Postgres"

# --- case 12: a retained passphrase with a carriage return survives --force -

dir="$WORK/force-carriage-return"
gen_env "$dir"
# The seed is what an installation written by an older renderer can hold: a
# double-quoted value carrying the `\r` escape. The repository's reader decodes
# it to a real CR, which is a line break for str.splitlines(), so writing the
# character back literally splits the assignment and the next read returns
# `alpha`.
printf '%s\n' 'PGBACKREST_REPO1_CIPHER_PASS="alpha\rbravo"' >"$IBEX_V1_ENV_FILE"
chmod 0600 "$IBEX_V1_ENV_FILE"
before="$(env_read PGBACKREST_REPO1_CIPHER_PASS)"
[[ "$before" == *$'\r'* ]] \
  || fail "carriage return: the fixture .env did not decode to a value containing CR"
if ! bash "$GEN" --force >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "carriage return: generator exited non-zero"
fi
after="$(env_read PGBACKREST_REPO1_CIPHER_PASS)"
# Byte-identical, not merely equal after normalisation: a CR that became a
# newline, or a trailing byte that vanished, would still decrypt nothing.
if ! printf '%s' "$after" | cmp -s - <(printf '%s' "$before"); then
  fail "carriage return: --force changed the value the repository's dotenv reader decodes"
fi
if grep -q $'\r' "$IBEX_V1_ENV_FILE"; then
  fail "carriage return: the retained passphrase was written back with a literal CR, which splits the assignment across lines"
fi
if grep -qF -- "$before" "$dir/out.log"; then
  fail "carriage return: a credential value appeared in the output"
fi
pass "--force preserves a passphrase containing a carriage return byte for byte"

# --- case 13: an environment-only invocation needs no profile dotenv --------

dir="$WORK/restore-env-only"
mkdir -p "$dir"
printf '[global]\nrepo1-type=s3\n' >"$dir/pgbackrest.conf"
write_stub "$dir/stub-engine"
STUB_LOG="$dir/calls.log"
STUB_ENV_REPORT="$dir/env-report.txt"
export STUB_LOG STUB_ENV_REPORT
: >"$STUB_LOG"
: >"$STUB_ENV_REPORT"

# Recovery with all three credentials supplied through the environment and no
# profile .env available at all (a recovery host, a break-glass shell). The
# loader must not demand the file, the probe must still prove delivery intact,
# and Postgres must be stopped only after that.
cipher="$(new_cipher)"
s3_key="$(new_cipher)"
s3_secret="$(new_cipher)"
# shellcheck disable=SC2030,SC2031
if ! (
  export PGBACKREST_REPO1_CIPHER_PASS="$cipher"
  export PGBACKREST_REPO1_S3_KEY="$s3_key"
  export PGBACKREST_REPO1_S3_KEY_SECRET="$s3_secret"
  export PGBACKREST_CONF="$dir/pgbackrest.conf"
  export PGBACKREST_STANZA=ibex-main
  export PGBACKREST_COMPOSE_VOLUME=stubvol
  export COMPOSE_FILE="$ROOT_DIR/infra/compose/v1-single-node/compose.yml"
  export IBEX_V1_ENV="$dir/absent.env"
  export IBEX_CONTAINER_CLI="$dir/stub-engine"
  bash "$RESTORE"
) >"$dir/out.log" 2>&1; then
  cat "$dir/out.log" >&2
  fail "environment-only credentials: the restore refused although all three were supplied and no .env was needed"
fi
[[ ! -e "$dir/absent.env" ]] \
  || fail "environment-only credentials: the case created the dotenv it exists to omit"
[[ "$(stub_report_value ENVFILE_KEYS)" == "3" ]] \
  || fail "environment-only credentials: the credential file did not carry all three credentials"
expected_sha="$(printf '%s' "$cipher" | sha256sum | awk '{print $1}')"
[[ "$(stub_report_value ENVFILE_CIPHER_SHA)" == "$expected_sha" ]] \
  || fail "environment-only credentials: the container did not receive the passphrase the environment held"
probe_line="$(grep -n -- '--entrypoint sh' "$STUB_LOG" | head -n1 | cut -d: -f1)"
stop_line="$(grep -n -- ' stop postgres' "$STUB_LOG" | head -n1 | cut -d: -f1)"
[[ -n "$probe_line" && -n "$stop_line" && "$probe_line" -lt "$stop_line" ]] \
  || fail "environment-only credentials: Postgres was not stopped after credential delivery was proven"
for secret in "$cipher" "$s3_key" "$s3_secret"; do
  if grep -qF -- "$secret" "$dir/out.log"; then
    fail "environment-only credentials: a credential value appeared in the output"
  fi
done
pass "an environment-only v1 invocation proceeds without a profile .env and proves delivery before stopping Postgres"

echo "v1 backup credential tests: PASS ($PASSED cases)"
