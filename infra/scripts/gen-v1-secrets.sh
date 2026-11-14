#!/usr/bin/env bash
# gen-v1-secrets.sh — generate the v1-single-node profile's .env and secrets.
#
# ADR-0097 §2/§4/§5. The profile needs one operator-owned .env plus a directory
# of file secrets (TLS leaves, the per-install CA, JWT keys, policy-signing key).
# This script creates both without ever printing a secret value.
#
# Defaults:
#   env file     infra/compose/v1-single-node/.env               (mode 0600)
#   secrets dir  infra/compose/v1-single-node/secrets/          (mode 0700)
#   certs dir    infra/compose/v1-single-node/certs/            (canonical TLS)
#
# Overrides for testing (no repository path is touched):
#   IBEX_V1_ENV_FILE=/tmp/x/.env
#   IBEX_V1_SECRETS_DIR=/tmp/x/secrets
#   IBEX_V1_CERTS_DIR=/tmp/x/certs
#   IBEX_V1_PGBACKREST_CONF=/tmp/x/pgbackrest.conf
#
# Idempotent: existing non-empty secret values and valid keypairs are kept.
# --force rewrites .env from infra/compose/v1-single-node/.env.example and regenerates every
# secret and keypair. It does NOT rotate the TLS CA; gen-v1-tls.sh reuses a valid
# CA and only reissues missing or invalid leaves. Use gen-v1-tls.sh --force when
# a CA rotation is actually intended.
#
# --force also preserves PGBACKREST_REPO1_CIPHER_PASS when the previous .env had
# one: that passphrase is the only key to every object in the backup repository,
# so regenerating it would orphan every existing backup. A rotation is requested
# explicitly with --rotate-pgbackrest-cipher, which refuses while a value exists
# unless IBEX_PGBACKREST_ALLOW_CIPHER_ROTATION=1 is set.
#
# An unreadable .env is a hard error, not an empty value: reading it as empty
# would generate a new passphrase and orphan every existing backup. The
# replacement .env is staged in a temporary file with the retained passphrase
# already written, then renamed into place, so an interruption between the two
# cannot leave .env without the only copy of the key.
#
# The container copies in the secrets directory are mode 0444 so uid 10001 can
# read them. The directory itself is 0700; that is the access boundary. Canonical
# TLS private keys under certs/ stay 0600.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${IBEX_V1_ENV_FILE:-$ROOT_DIR/infra/compose/v1-single-node/.env}"
SECRETS_DIR="${IBEX_V1_SECRETS_DIR:-$ROOT_DIR/infra/compose/v1-single-node/secrets}"
CERTS_DIR="${IBEX_V1_CERTS_DIR:-$ROOT_DIR/infra/compose/v1-single-node/certs}"
# The bootstrap PAT must survive the one-shot container's exit. It is written to
# a host bind mount (0700) rather than a container tmpfs, so a first install
# cannot lose its only admin credential. The path is fixed: the Compose mount
# and `make v1-bootstrap-pat` must resolve the same directory.
BOOTSTRAP_DIR="$ROOT_DIR/infra/compose/v1-single-node/bootstrap"
EXAMPLE_ENV="$ROOT_DIR/infra/compose/v1-single-node/.env.example"
TLS_SCRIPT="$ROOT_DIR/infra/scripts/gen-v1-tls.sh"
# The stanza config is generated output, not a secret. The override exists so
# the regression tests never rewrite the file a running profile mounts.
PGBACKREST_CONF_DEST="${IBEX_V1_PGBACKREST_CONF:-$ROOT_DIR/infra/backup/pgbackrest/pgbackrest.conf}"

usage() {
  cat <<'EOF'
Usage: gen-v1-secrets.sh [--force] [--rotate-pgbackrest-cipher]

Creates the v1-single-node .env and file secrets.
  --force   rewrite .env from infra/compose/v1-single-node/.env.example and regenerate all
            secrets and keypairs (the TLS CA is not rotated). PGBACKREST_REPO1_CIPHER_PASS
            is preserved when one exists: rotating it would make every existing backup
            unreadable.
  --rotate-pgbackrest-cipher
            generate a new PGBACKREST_REPO1_CIPHER_PASS. Refused when a value already
            exists, because that passphrase encrypts the existing repository. Set
            IBEX_PGBACKREST_ALLOW_CIPHER_ROTATION=1 only after recording the old pass and
            accepting that backups encrypted with it become unreadable.
EOF
}

FORCE=0
ROTATE_CIPHER=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --rotate-pgbackrest-cipher) ROTATE_CIPHER=1 ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "gen-v1-secrets.sh: unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v openssl >/dev/null 2>&1 || {
  echo "gen-v1-secrets.sh: openssl is required" >&2
  exit 1
}
[[ -f "$EXAMPLE_ENV" ]] || {
  echo "gen-v1-secrets.sh: template not found: $EXAMPLE_ENV" >&2
  exit 1
}
[[ -x "$TLS_SCRIPT" ]] || {
  echo "gen-v1-secrets.sh: TLS generator not found or not executable: $TLS_SCRIPT" >&2
  exit 1
}

# A mistaken override must never chmod the repository root or the filesystem
# root: the final step sets every file in the secrets directory to 0444.
resolve_path() {
  local target="$1"
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$target"
}
root_real="$(resolve_path "$ROOT_DIR")"
for dir in "$SECRETS_DIR" "$CERTS_DIR" "$BOOTSTRAP_DIR"; do
  real="$(resolve_path "$dir")"
  if [[ "$real" == "/" || "$real" == "$root_real" || "$real" == "$root_real/.git" || "$real" == "$root_real"/.git/* ]]; then
    echo "gen-v1-secrets.sh: refusing unsafe directory override: $dir (resolved $real)" >&2
    exit 1
  fi
done

# Never let a permissive ambient umask leak secret files, and never let a
# partial write survive an interrupted run.
umask 077

env_value() {
  local key="$1"
  python3 "$ROOT_DIR/infra/scripts/lib/dotenv.py" "$key" <"$ENV_FILE"
}

# env_set_file writes one key into an arbitrary env file through a temporary
# file in the same directory and an atomic rename. A failure removes the partial
# write and leaves the target untouched.
#
# The value is serialised with the quoting and escaping that
# infra/scripts/lib/dotenv.py decodes -- the reader every lookup here and in
# dev-tool.sh uses, and the same rules Compose applies -- so the effective value
# is byte-identical before and after a rewrite.
# Writing it bare is only safe for a value that cannot be misread: Compose ends
# an unquoted value at the first whitespace followed by `#`, strips surrounding
# whitespace, and interpolates `$`. A retained passphrase such as
# `fixture # suffix` written bare therefore reads back as `fixture`, and the
# profile would archive and restore with a different key than the one the
# repository was encrypted with.
env_set_file() {
  local path="$1" key="$2" value="$3" tmp
  tmp="$(mktemp "${path}.tmp.XXXXXX")"
  if ! KEY="$key" VALUE="$value" python3 - "$path" >"$tmp" <<'PY'
import os
import re
import sys

SAFE = re.compile(r"[A-Za-z0-9_./:@+-]+")
# Every escape below is one the repository's reader decodes
# (infra/scripts/lib/dotenv.py: ESCAPES). A literal CR is not cosmetic: this
# function reads the file back with universal newlines, so the next write pass
# turns a literal CR into a real line break, splits the assignment in two and
# leaves its tail as an orphan line -- after which the retained passphrase, the
# only key to every backup object, reads back as `alpha` and every backup
# encrypted with it becomes unreadable. `\t` needs no entry: a literal tab is
# not a line break and survives both readers unchanged inside the quotes.
ESCAPES = (
    ("\\", "\\\\"),
    ('"', '\\"'),
    ("$", "\\$"),
    ("\n", "\\n"),
    ("\r", "\\r"),
)


def render(value: str) -> str:
    """Serialise a value so the dotenv reader returns it unchanged."""
    if value == "" or SAFE.fullmatch(value):
        return value
    for literal, escaped in ESCAPES:
        value = value.replace(literal, escaped)
    return f'"{value}"'


path = sys.argv[1]
key = os.environ["KEY"]
value = os.environ["VALUE"]
pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=")
lines = []
try:
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
except FileNotFoundError:
    pass
found = False
out = []
for line in lines:
    if pattern.match(line):
        if not found:
            out.append(f"{key}={render(value)}")
            found = True
        continue
    out.append(line)
if not found:
    out.append(f"{key}={render(value)}")
sys.stdout.write("\n".join(out) + "\n")
PY
  then
    rm -f "$tmp"
    return 1
  fi
  chmod 0600 "$tmp"
  mv -f "$tmp" "$path"
}

env_set() {
  env_set_file "$ENV_FILE" "$1" "$2"
}

# ensure_env_file creates .env from the template when it is absent, and under
# --force replaces it with a fresh template.
#
# The replacement is staged beside the original and renamed into place only once
# it is complete. The retained repository passphrase is written into the staged
# file *before* the rename: it is the only key to every object in the backup
# repository, so an interruption between "template written" and "passphrase
# written" must not be able to leave .env holding no copy of it. Any staging
# failure removes the temporary file and exits with the original untouched.
ensure_env_file() {
  local env_dir tmp
  env_dir="$(dirname "$ENV_FILE")"
  mkdir -p "$env_dir"
  # Do not chmod the env directory: the default is the repository root, and
  # narrowing it would break the working tree. The file itself is 0600.

  if [[ -f "$ENV_FILE" && "$FORCE" -eq 0 ]]; then
    chmod 0600 "$ENV_FILE"
    return 0
  fi

  tmp="$(mktemp "${ENV_FILE}.new.XXXXXX")"
  chmod 0600 "$tmp"
  if ! cp "$EXAMPLE_ENV" "$tmp"; then
    rm -f "$tmp"
    echo "gen-v1-secrets.sh: could not stage a replacement .env; $ENV_FILE is unchanged" >&2
    exit 1
  fi
  if [[ -n "$PREVIOUS_CIPHER_PASS" ]]; then
    if ! env_set_file "$tmp" PGBACKREST_REPO1_CIPHER_PASS "$PREVIOUS_CIPHER_PASS"; then
      rm -f "$tmp"
      echo "gen-v1-secrets.sh: could not carry PGBACKREST_REPO1_CIPHER_PASS into the staged .env; $ENV_FILE is unchanged" >&2
      exit 1
    fi
  fi
  mv -f "$tmp" "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
  if [[ "$FORCE" -eq 1 ]]; then
    echo "gen-v1-secrets.sh: --force rewrote $ENV_FILE from the template (repository passphrase preserved)" >&2
  fi
}

log_item() {
  printf '  %-40s %s\n' "$1" "$2"
}

summary_item() {
  printf '  %-24s %s\n' "$1" "$2"
}

# set_secret fills an empty value; --force replaces a non-empty one.
set_secret() {
  local key="$1" value="$2" current
  current="$(env_value "$key")"
  if [[ "$FORCE" -eq 1 || -z "$current" ]]; then
    env_set "$key" "$value"
    log_item "$key" "generated"
  else
    log_item "$key" "kept"
  fi
}

# set_derived always rewrites a non-secret value that is computed from other
# settings, so a changed port cannot leave a stale value behind.
set_derived() {
  local key="$1" value="$2"
  env_set "$key" "$value"
  log_item "$key" "$value"
}

# set_default fills a value that the operator may override. Unlike set_derived
# it never rewrites a non-empty entry, so a changed endpoint survives a rerun.
set_default() {
  local key="$1" value="$2" current
  current="$(env_value "$key")"
  if [[ -z "$current" ]]; then
    env_set "$key" "$value"
    log_item "$key" "$value"
  else
    log_item "$key" "kept"
  fi
}

gen_hex() {
  openssl rand -hex 32
}

# gen_pat produces a PAT-shaped service token. The memory service validates
# every inbound bearer through AuthService, so an arbitrary shared string is
# rejected; the bootstrap inserts this value's Argon2id hash as a scoped
# service_token (MemoryRead|MemoryWrite).
gen_pat() {
  local token_uuid secret
  token_uuid="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  secret="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
  printf 'ibex_pat_%s_%s' "$token_uuid" "$secret"
}

gen_rsa_pair() {
  local private="$1" public="$2" label="$3" priv_pub pub_text
  if [[ "$FORCE" -eq 0 && -f "$private" && -f "$public" ]]; then
    priv_pub="$(openssl pkey -in "$private" -pubout 2>/dev/null)" || {
      echo "gen-v1-secrets.sh: $label private key is unreadable; rerun with --force" >&2
      exit 1
    }
    pub_text="$(cat "$public")"
    if [[ "$priv_pub" != "$pub_text" ]]; then
      echo "gen-v1-secrets.sh: $label keypair does not match; rerun with --force" >&2
      exit 1
    fi
    log_item "$label" "kept"
    return 0
  fi
  if [[ "$FORCE" -eq 0 && ( -f "$private" || -f "$public" ) ]]; then
    echo "gen-v1-secrets.sh: incomplete $label keypair; rerun with --force" >&2
    exit 1
  fi

  # A previous run left container copies at 0444. Remove them before openssl
  # opens the output path for writing.
  rm -f "$private" "$public"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$private" 2>/dev/null
  openssl pkey -in "$private" -pubout -out "$public" 2>/dev/null
  chmod 0600 "$private"
  chmod 0444 "$public"

  if ! openssl pkey -in "$private" -noout 2>/dev/null; then
    echo "gen-v1-secrets.sh: generated $label private key is unreadable" >&2
    exit 1
  fi
  log_item "$label" "generated"
}

install_secret_copy() {
  local src="$1" dest="$2"
  if [[ ! -s "$src" ]]; then
    echo "gen-v1-secrets.sh: missing source secret: $src" >&2
    exit 1
  fi
  if [[ "$src" -ef "$dest" ]]; then
    chmod 0444 "$dest"
    return 0
  fi
  # Write a 0444 copy through a temporary file and rename it into place. A
  # direct cp onto a previous 0444 copy would fail or leave a partial file if
  # interrupted.
  local tmp
  tmp="$(mktemp "$(dirname "$dest")/.copy.XXXXXX")"
  cp "$src" "$tmp"
  chmod 0444 "$tmp"
  mv -f "$tmp" "$dest"
}

# write_pgbackrest_conf renders the pgBackRest stanza config from .env.
#
# The file is NOT a secret container and is not treated as one: it is bind
# mounted read-only into the postgres container, which runs as uid 999, so it
# has to be readable by that uid. Repository credentials are therefore supplied
# as PGBACKREST_* environment variables by compose and never appear here.
#
# It is rewritten on every run so the endpoint, bucket, and cluster user cannot
# drift from .env.
write_pgbackrest_conf() {
  local dest="$PGBACKREST_CONF_DEST"
  local endpoint bucket user tmp
  endpoint="$(env_value IBEX_OBJECTSTORE_ENDPOINT)"
  endpoint="${endpoint:-http://objectstore:9000}"
  # The bucket is a fixed name, not an override. objectstore-init creates
  # exactly `store/ibex-pgbackrest` (infra/compose/v1-single-node/compose.yml)
  # and pgBackRest never creates a bucket, so any other value here would point
  # the repository at a bucket that does not exist and the failure would only
  # surface later as an archive-push error. The previous read from the process
  # environment was worse than useless: a value exported in the shell was used
  # while a value in .env (where every other input is read from) was ignored.
  # Changing the bucket means changing this literal and the one-shot together.
  bucket="ibex-pgbackrest"
  user="$(env_value POSTGRES_USER)"
  user="${user:-ibex}"

  # Values land in an INI file unquoted. Refuse anything that could open a new
  # section or a new key instead of writing a config that silently redirects
  # the repository.
  local value
  for value in "$endpoint" "$bucket" "$user"; do
    if ! [[ "$value" =~ ^[A-Za-z0-9._:/@-]+$ ]]; then
      echo "gen-v1-secrets.sh: refusing unsafe pgBackRest config value: $value" >&2
      exit 1
    fi
  done

  mkdir -p "$(dirname "$dest")"
  tmp="$(mktemp "$(dirname "$dest")/.pgbackrest.conf.XXXXXX")"
  cat >"$tmp" <<EOF
# Generated by infra/scripts/gen-v1-secrets.sh from
# infra/compose/v1-single-node/.env. Do not edit: rerun \`make v1-secrets\`.
#
# Credentials are environment-only. compose supplies
#   PGBACKREST_REPO1_S3_KEY
#   PGBACKREST_REPO1_S3_KEY_SECRET
#   PGBACKREST_REPO1_CIPHER_PASS
# so this file can stay world-readable inside the postgres container.
#
# archive-async stays off: a failed archive-push must block WAL recycling so
# pg_stat_archiver shows the failure instead of hiding it behind a retry queue.
[global]
repo1-type=s3
repo1-path=/pgbackrest
repo1-s3-bucket=$bucket
repo1-s3-endpoint=$endpoint
repo1-s3-region=us-east-1
repo1-s3-uri-style=path
repo1-cipher-type=aes-256-cbc
repo1-retention-full=2
compress-type=lz4
process-max=2
start-fast=y
archive-async=n

[ibex-main]
pg1-path=/var/lib/postgresql/data
pg1-port=5432
pg1-user=$user
EOF
  chmod 0644 "$tmp"
  mv -f "$tmp" "$dest"
  log_item "pgbackrest stanza config" "$dest"
}

# write_policy_key_set renders the proxy's IBEX_PROXY_POLICY_PUBLIC_KEYS JSON.
# The proxy refuses to build its router in staging/production without a
# verifier, and AuthService signs with key id "v1" by default
# (IBEX_AUTH_POLICY_SIGNING_KEY_ID). The file is regenerated from the current
# public key so a rotated keypair cannot leave a stale verifier behind.
write_policy_key_set() {
  local public="$1" dest="$2" tmp
  if [[ ! -s "$public" ]]; then
    echo "gen-v1-secrets.sh: missing policy public key: $public" >&2
    exit 1
  fi
  tmp="$(mktemp "$(dirname "$dest")/.keyset.XXXXXX")"
  python3 - "$public" >"$tmp" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    pem = handle.read()
json.dump({"v1": pem}, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
  chmod 0444 "$tmp"
  mv -f "$tmp" "$dest"
}

echo "v1-single-node secrets"
echo "  env file:     $ENV_FILE"
echo "  secrets dir:  $SECRETS_DIR"
echo "  certs dir:    $CERTS_DIR"
echo

# --force rewrites .env from the template, which drops the repository cipher
# passphrase. Capture it first: it is the only key to every object in the
# repository, so losing it makes existing backups unreadable. --force reuses it;
# only --rotate-pgbackrest-cipher replaces it.
#
# A failed read is not an absent value. `|| true` used to turn an unreadable
# .env into an empty passphrase, after which --force rewrote the file and the
# generator produced a new key: every existing backup silently orphaned. An
# unreadable file therefore aborts here, before ensure_env_file can replace it.
PREVIOUS_CIPHER_PASS=""
if [[ -e "$ENV_FILE" || -L "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "gen-v1-secrets.sh: $ENV_FILE exists but is not a regular file; refusing to continue" >&2
    exit 1
  fi
  if ! PREVIOUS_CIPHER_PASS="$(env_value PGBACKREST_REPO1_CIPHER_PASS)"; then
    cat >&2 <<EOF
gen-v1-secrets.sh: cannot read $ENV_FILE.
PGBACKREST_REPO1_CIPHER_PASS may be set there, and it is the only key to every
object in the backup repository. Refusing to continue: generating a new
passphrase would leave the repository intact but unreadable, and rewriting .env
would discard the old one. Fix the ownership/permissions on the file and rerun.
EOF
    exit 1
  fi
fi
if (( ROTATE_CIPHER )) && [[ -n "$PREVIOUS_CIPHER_PASS" ]] \
  && [[ "${IBEX_PGBACKREST_ALLOW_CIPHER_ROTATION:-0}" != "1" ]]; then
  cat >&2 <<EOF
gen-v1-secrets.sh: refusing to rotate PGBACKREST_REPO1_CIPHER_PASS.
The existing passphrase encrypts every object in the backup repository, so a new
one makes every existing backup unreadable. Decommission or empty the repository
and remove PGBACKREST_REPO1_CIPHER_PASS from $ENV_FILE first, or set
IBEX_PGBACKREST_ALLOW_CIPHER_ROTATION=1 after recording the old pass and
accepting that existing backups become unreadable.
EOF
  exit 1
fi

ensure_env_file

echo "env secrets:"
set_secret POSTGRES_PASSWORD "$(gen_hex)"
# Capability-login passwords. Their plaintext lives only in this .env and is
# read by the one-shot `provision` service, which writes one SCRAM verifier per
# role in a single transaction. Each must differ from POSTGRES_PASSWORD (the
# owner credential) and from the others; provision refuses to commit otherwise,
# so a collision fails the profile instead of silently weakening it.
set_secret IBEX_RUNTIME_DB_PASSWORD "$(gen_hex)"
set_secret IBEX_AUTH_DB_PASSWORD "$(gen_hex)"
set_secret IBEX_WORKER_DB_PASSWORD "$(gen_hex)"
set_secret IBEX_BOOTSTRAP_DB_PASSWORD "$(gen_hex)"
set_secret REDIS_PASSWORD "$(gen_hex)"
set_secret IBEX_CREDENTIALS_MASTER_KEY "$(openssl rand -base64 32 | tr -d '\n')"
set_secret IBEX_AUTH_SERVICE_TOKEN "$(gen_hex)"
set_secret IBEX_CONTEXT_GRPC_SERVICE_TOKEN "$(gen_hex)"
set_secret IBEX_MEMORY_API_TOKEN "$(gen_pat)"
set_secret IBEX_EMBEDDING_API_TOKEN "$(gen_hex)"
set_secret IBEX_WORKER_ENQUEUE_API_TOKEN "$(gen_hex)"
set_secret DASHBOARD_CSRF_SECRET "$(gen_hex)"
set_secret IBEX_OPERATOR_CURSOR_SECRET "$(gen_hex)"
# Backup repository identity. One credential pair is shared by the object
# store, the archive command, and the restore path; there is no second
# principal to rotate. The values are opaque to the store: they are the MinIO
# root identity in this profile and work unchanged against any S3-compatible
# endpoint the operator repoints repo1-s3-endpoint at.
set_secret IBEX_OBJECTSTORE_ACCESS_KEY "$(gen_hex)"
set_secret IBEX_OBJECTSTORE_SECRET_KEY "$(openssl rand -hex 32)"
# Repository cipher passphrase. pgBackRest's only supported repo cipher is
# aes-256-cbc (see infra/backup/pgbackrest/pgbackrest.conf.example); the
# passphrase never enters the generated config, only the container environment.
#
# A rerun reuses the previous value. Regenerating it silently would leave the
# repository intact but unreadable, which is worse than a failed rotation: the
# operator would discover it at restore time.
if (( ROTATE_CIPHER )); then
  env_set PGBACKREST_REPO1_CIPHER_PASS "$(openssl rand -hex 32)"
  log_item PGBACKREST_REPO1_CIPHER_PASS "rotated"
  echo "gen-v1-secrets.sh: WARNING: rotated PGBACKREST_REPO1_CIPHER_PASS; backups encrypted with the previous value are unreadable" >&2
elif [[ -n "$PREVIOUS_CIPHER_PASS" ]]; then
  set_secret PGBACKREST_REPO1_CIPHER_PASS "$PREVIOUS_CIPHER_PASS"
else
  set_secret PGBACKREST_REPO1_CIPHER_PASS "$(openssl rand -hex 32)"
fi
# The in-profile repository endpoint. Override in .env to point at an external
# S3-compatible store; the value is written into the generated stanza config on
# the next run.
#
# The in-profile object store moved from SeaweedFS:8333 to MinIO:9000. A .env
# written by an older generator still carries the old in-profile default, which
# would point every archive-push at a service that no longer exists. Rewrite
# only that exact value: any other endpoint is an operator override and is kept.
if [[ "$(env_value IBEX_OBJECTSTORE_ENDPOINT)" == "http://objectstore:8333" ]]; then
  env_set IBEX_OBJECTSTORE_ENDPOINT "http://objectstore:9000"
  log_item IBEX_OBJECTSTORE_ENDPOINT "migrated from the SeaweedFS default"
fi
set_default IBEX_OBJECTSTORE_ENDPOINT "http://objectstore:9000"

# CORS/CSRF trusts exactly the browser origin the edge serves. Trusting bare
# https://localhost on a non-443 port would also trust a different local service
# that happens to bind 443.
edge_port="${IBEX_EDGE_PORT:-}"
if [[ -z "$edge_port" ]]; then
  edge_port="$(env_value IBEX_EDGE_PORT)"
fi
edge_port="${edge_port:-443}"
env_set IBEX_EDGE_PORT "$edge_port"
if [[ "$edge_port" == "443" ]]; then
  set_derived IBEX_ALLOWED_ORIGINS "https://localhost"
else
  set_derived IBEX_ALLOWED_ORIGINS "https://localhost:${edge_port}"
fi

mkdir -p "$SECRETS_DIR"
chmod 0700 "$SECRETS_DIR"
mkdir -p "$BOOTSTRAP_DIR"
chmod 0700 "$BOOTSTRAP_DIR"

if [[ "$SECRETS_DIR" -ef "$CERTS_DIR" ]]; then
  echo "gen-v1-secrets.sh: secrets dir and certs dir are the same; canonical TLS keys will become container copies (0444)" >&2
fi

echo
echo "keypairs:"
gen_rsa_pair "$SECRETS_DIR/jwt_private.pem" "$SECRETS_DIR/jwt_public.pem" "jwt keypair"
gen_rsa_pair "$SECRETS_DIR/policy_private.pem" "$SECRETS_DIR/policy_public.pem" "policy signing keypair"
write_policy_key_set "$SECRETS_DIR/policy_public.pem" "$SECRETS_DIR/policy_public_keys.json"
log_item "proxy policy key set" "written"

echo
echo "TLS material:"
# The generator is idempotent: it reuses a valid CA and only reissues missing or
# invalid leaves. It never rotates the CA without --force, which this script
# deliberately does not pass.
bash "$TLS_SCRIPT" "$CERTS_DIR" >/dev/null

install_secret_copy "$CERTS_DIR/ca.crt" "$SECRETS_DIR/ca.crt"
install_secret_copy "$CERTS_DIR/auth.crt" "$SECRETS_DIR/auth.crt"
install_secret_copy "$CERTS_DIR/auth.key" "$SECRETS_DIR/auth.key"
install_secret_copy "$CERTS_DIR/edge.crt" "$SECRETS_DIR/edge.crt"
install_secret_copy "$CERTS_DIR/edge.key" "$SECRETS_DIR/edge.key"
log_item "tls leaves + ca" "copied"

echo
echo "backup repository:"
write_pgbackrest_conf

# Track the certificate material so a renewal can trigger a targeted container
# recreation: the auth server must not keep serving a replaced certificate.
fingerprint_file="$CERTS_DIR/.cert-fingerprint"
current_fingerprint="$(cat "$SECRETS_DIR/ca.crt" "$SECRETS_DIR/auth.crt" "$SECRETS_DIR/edge.crt" | sha256sum | awk '{print $1}')"
if [[ -f "$fingerprint_file" && "$(cat "$fingerprint_file")" != "$current_fingerprint" ]]; then
  touch "$CERTS_DIR/.certificates-changed"
  log_item "certificate change" "detected; v1-up will recreate the mounted services"
fi
printf '%s\n' "$current_fingerprint" >"$fingerprint_file"
chmod 0600 "$fingerprint_file"

# Container secret copies are readable by the non-root service UIDs. The 0700
# directory is the real boundary; do not widen it.
find "$SECRETS_DIR" -maxdepth 1 -type f -exec chmod 0444 {} +
chmod 0700 "$SECRETS_DIR"
chmod 0600 "$ENV_FILE"

echo
echo "summary (values not shown):"
summary_item ".env" "$ENV_FILE (mode $(stat -c %a "$ENV_FILE"))"
summary_item "secrets dir" "$SECRETS_DIR (mode $(stat -c %a "$SECRETS_DIR"))"
summary_item "bootstrap dir" "$BOOTSTRAP_DIR (mode $(stat -c %a "$BOOTSTRAP_DIR"); PAT file 0600)"
summary_item "tls certs" "$CERTS_DIR"
summary_item "ca sha256" "$(openssl x509 -in "$CERTS_DIR/ca.crt" -noout -fingerprint -sha256 | sed 's/^.*=//')"
echo
echo "Next: make v1-up"
