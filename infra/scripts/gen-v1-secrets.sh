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
#
# Idempotent: existing non-empty secret values and valid keypairs are kept.
# --force rewrites .env from infra/compose/v1-single-node/.env.example and regenerates every
# secret and keypair. It does NOT rotate the TLS CA; gen-v1-tls.sh reuses a valid
# CA and only reissues missing or invalid leaves. Use gen-v1-tls.sh --force when
# a CA rotation is actually intended.
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
EXAMPLE_ENV="$ROOT_DIR/infra/compose/v1-single-node/.env.example"
TLS_SCRIPT="$ROOT_DIR/infra/scripts/gen-v1-tls.sh"

usage() {
  cat <<'EOF'
Usage: gen-v1-secrets.sh [--force]

Creates the v1-single-node .env and file secrets.
  --force   rewrite .env from infra/compose/v1-single-node/.env.example and regenerate all
            secrets and keypairs (the TLS CA is not rotated)
EOF
}

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
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
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}
root_real="$(resolve_path "$ROOT_DIR")"
for dir in "$SECRETS_DIR" "$CERTS_DIR"; do
  real="$(resolve_path "$dir")"
  case "$real" in
    / | "$root_real" | "$root_real/.git" | "$root_real"/.git/*)
      echo "gen-v1-secrets.sh: refusing unsafe directory override: $dir (resolved $real)" >&2
      exit 1
      ;;
    *) ;;
  esac
done

# Never let a permissive ambient umask leak secret files, and never let a
# partial write survive an interrupted run.
umask 077

env_value() {
  local key="$1"
  KEY="$key" python3 - "$ENV_FILE" <<'PY'
import os
import re
import sys

path = sys.argv[1]
key = os.environ["KEY"]
pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*)$")
value = ""
try:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            match = pattern.match(line.rstrip("\n"))
            if not match:
                continue
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
except FileNotFoundError:
    pass
print(value)
PY
}

env_set() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
  KEY="$key" VALUE="$value" python3 - "$ENV_FILE" >"$tmp" <<'PY'
import os
import re
import sys

path = sys.argv[1]
key = os.environ["KEY"]
value = os.environ["VALUE"]
pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
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
            out.append(f"{key}={value}")
            found = True
        continue
    out.append(line)
if not found:
    out.append(f"{key}={value}")
sys.stdout.write("\n".join(out) + "\n")
PY
  chmod 0600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

ensure_env_file() {
  local env_dir
  env_dir="$(dirname "$ENV_FILE")"
  mkdir -p "$env_dir"
  # Do not chmod the env directory: the default is the repository root, and
  # narrowing it would break the working tree. The file itself is 0600.

  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$EXAMPLE_ENV" "$ENV_FILE"
    chmod 0600 "$ENV_FILE"
  elif [[ "$FORCE" -eq 1 ]]; then
    cp "$EXAMPLE_ENV" "$ENV_FILE"
    chmod 0600 "$ENV_FILE"
    echo "gen-v1-secrets.sh: --force rewrote $ENV_FILE from the template" >&2
  else
    chmod 0600 "$ENV_FILE"
  fi
}

log_item() {
  printf '  %-40s %s\n' "$1" "$2"
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

ensure_env_file

echo "env secrets:"
set_secret POSTGRES_PASSWORD "$(gen_hex)"
set_secret REDIS_PASSWORD "$(gen_hex)"
set_secret IBEX_CREDENTIALS_MASTER_KEY "$(openssl rand -base64 32 | tr -d '\n')"
set_secret IBEX_AUTH_SERVICE_TOKEN "$(gen_hex)"
set_secret IBEX_CONTEXT_GRPC_SERVICE_TOKEN "$(gen_hex)"
set_secret IBEX_MEMORY_API_TOKEN "$(gen_pat)"
set_secret IBEX_EMBEDDING_API_TOKEN "$(gen_hex)"
set_secret IBEX_WORKER_ENQUEUE_API_TOKEN "$(gen_hex)"
set_secret DASHBOARD_CSRF_SECRET "$(gen_hex)"
set_secret IBEX_OPERATOR_CURSOR_SECRET "$(gen_hex)"

# CORS/CSRF trusts exactly the browser origin the edge serves. Trusting bare
# https://localhost on a non-443 port would also trust a different local service
# that happens to bind 443.
edge_port="$(env_value IBEX_EDGE_PORT)"
edge_port="${edge_port:-443}"
env_set IBEX_EDGE_PORT "$edge_port"
if [[ "$edge_port" == "443" ]]; then
  set_derived IBEX_ALLOWED_ORIGINS "https://localhost"
else
  set_derived IBEX_ALLOWED_ORIGINS "https://localhost:${edge_port}"
fi

mkdir -p "$SECRETS_DIR"
chmod 0700 "$SECRETS_DIR"

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
printf '  %-24s %s\n' ".env" "$ENV_FILE (mode $(stat -c %a "$ENV_FILE"))"
printf '  %-24s %s\n' "secrets dir" "$SECRETS_DIR (mode $(stat -c %a "$SECRETS_DIR"))"
printf '  %-24s %s\n' "tls certs" "$CERTS_DIR"
printf '  %-24s %s\n' "ca sha256" "$(openssl x509 -in "$CERTS_DIR/ca.crt" -noout -fingerprint -sha256 | sed 's/^.*=//')"
echo
echo "Next: make v1-up"
