#!/usr/bin/env bash
# test-v1-backup-credentials.sh — regression tests for the v1 backup-repository
# credential chain.
#
# Two properties are guarded here because both protect the same secret:
#
#   1. gen-v1-secrets.sh never loses or silently replaces
#      PGBACKREST_REPO1_CIPHER_PASS. That passphrase is the only key to every
#      object in the repository: a regenerated one leaves the repository intact
#      but unreadable, and the operator finds out at restore time.
#   2. pgbackrest-restore.sh delivers the repository credentials to its
#      container in a way that survives a rootful `sudo -n podman` engine, and
#      proves delivery before it stops Postgres.
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
  run)
    log "RUN $*"
    envfile=""
    previous=""
    for arg in "$@"; do
      if [[ "$previous" == "--env-file" ]]; then
        envfile="$arg"
      fi
      previous="$arg"
    done
    if [[ -n "$envfile" ]]; then
      {
        printf 'ENVFILE_PATH=%s\n' "$envfile"
        printf 'ENVFILE_EXISTS=%s\n' "$([[ -f "$envfile" ]] && printf yes || printf no)"
        printf 'ENVFILE_MODE=%s\n' "$(stat -c %a "$envfile" 2>/dev/null || printf none)"
        printf 'ENVFILE_KEYS=%s\n' "$(grep -c '^PGBACKREST_REPO1_' "$envfile" 2>/dev/null || printf 0)"
        printf 'ENVFILE_LINES=%s\n' "$(grep -c . "$envfile" 2>/dev/null || printf 0)"
      } >>"$STUB_ENV_REPORT"
    fi
    exit "${STUB_RUN_RESULT:-0}"
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
[[ "$(stub_report_value ENVFILE_LINES)" == "3" ]] || fail "restore scratch: the credential file carried extra entries"
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

echo "v1 backup credential tests: PASS ($PASSED cases)"
