#!/usr/bin/env bash
# gen-v1-tls.sh — per-install TLS material for the v1-single-node profile.
#
# Generates a self-signed CA and two server leaves (AuthService and edge) under
# one directory. The files are secrets: never commit them and never print the
# private keys. ADR-0097 §4/§5 defines the transport contract this supports.
#
# Runtime mount contract:
#   - Mount only ca.crt plus the leaf pairs (auth.crt/auth.key,
#     edge.crt/edge.key) into containers.
#   - ca.key is operator-only. Never mount it into a container and never copy
#     it into an image. It must persist on the operator host so a missing or
#     broken leaf can be reissued without rotating the CA.
#
# Re-running without --force reuses a valid CA and regenerates only missing or
# invalid leaf pairs. The CA is rotated only with --force.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_TARGET="$REPO_ROOT/infra/compose/v1-single-node/certs"

usage() {
  cat <<'EOF'
Usage: gen-v1-tls.sh [--force] [--allow-foreign-dir] [TARGET_DIR]

Generates ca.crt/ca.key plus auth.crt/auth.key and edge.crt/edge.key.
TARGET_DIR defaults to infra/compose/v1-single-node/certs.

Without --force an existing valid CA is reused and only missing or invalid
leaf pairs are reissued. --force rotates the CA and reissues both leaves.

  --force             rotate the CA and regenerate both leaf pairs
  --allow-foreign-dir write into a TARGET_DIR owned by another user (warns)
EOF
}

FORCE=0
ALLOW_FOREIGN_DIR=0
TARGET_DIR=""
for arg in "$@"; do
  case "$arg" in
    --force)
      FORCE=1
      ;;
    --allow-foreign-dir)
      ALLOW_FOREIGN_DIR=1
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*)
      echo "gen-v1-tls.sh: unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$TARGET_DIR" ]]; then
        echo "gen-v1-tls.sh: too many arguments: $arg" >&2
        usage >&2
        exit 2
      fi
      TARGET_DIR="$arg"
      ;;
  esac
done

if [[ -z "$TARGET_DIR" ]]; then
  TARGET_DIR="$DEFAULT_TARGET"
fi

command -v openssl >/dev/null 2>&1 || {
  echo "gen-v1-tls.sh: openssl is required" >&2
  exit 1
}

CA_CRT="$TARGET_DIR/ca.crt"
CA_KEY="$TARGET_DIR/ca.key"
AUTH_CRT="$TARGET_DIR/auth.crt"
AUTH_KEY="$TARGET_DIR/auth.key"
EDGE_CRT="$TARGET_DIR/edge.crt"
EDGE_KEY="$TARGET_DIR/edge.key"

# Private keys are born unreadable to anyone but the owner. Set the umask
# before creating the directory: with a permissive ambient umask the directory
# would otherwise be world-writable while the keys stayed 0600, letting a local
# user replace ca.crt or a leaf.
#
# Refuse a pre-existing target directory owned by another user before writing
# anything: otherwise a planted ca.crt/ca.key (or a symlinked directory) would
# be adopted as this install's trust anchor.
FOREIGN_DIR=0
if [[ -d "$TARGET_DIR" ]]; then
  if ! dir_owner="$(stat -Lc %u "$TARGET_DIR" 2>/dev/null)"; then
    echo "gen-v1-tls.sh: cannot determine the owner of $TARGET_DIR" >&2
    exit 1
  fi
  if [[ "$dir_owner" != "$(id -u)" ]]; then
    if [[ "$ALLOW_FOREIGN_DIR" -eq 0 ]]; then
      echo "gen-v1-tls.sh: refusing to write into $TARGET_DIR: it is owned by uid $dir_owner, not $(id -u) (use --allow-foreign-dir to override)" >&2
      exit 1
    fi
    echo "WARNING: writing into $TARGET_DIR because it is owned by uid $dir_owner, not $(id -u)" >&2
    FOREIGN_DIR=1
  fi
elif [[ -e "$TARGET_DIR" ]]; then
  echo "gen-v1-tls.sh: $TARGET_DIR exists and is not a directory" >&2
  exit 1
fi

umask 077
mkdir -p "$TARGET_DIR"
if [[ "$FOREIGN_DIR" -eq 1 ]]; then
  # chmod would fail for a non-root caller and defeat the documented override.
  # The operator already accepted the foreign ownership explicitly; warn that
  # the mode cannot be tightened and continue.
  echo "WARNING: cannot tighten permissions on $TARGET_DIR; it is owned by another user" >&2
else
  chmod 0700 "$TARGET_DIR"
  # Re-assert modes on the reuse path (the early exit below skips generation),
  # so a previously loosened directory or key file cannot keep its old mode.
  for f in "$CA_KEY" "$AUTH_KEY" "$EDGE_KEY"; do
    if [[ -f "$f" ]]; then
      chmod 0600 "$f"
    fi
  done
fi

# run_openssl keeps the generation output quiet (it contains no key material,
# only progress banners) while still surfacing the full diagnostics on failure.
run_openssl() {
  local log
  log="$(mktemp)"
  if ! "$@" >/dev/null 2>"$log"; then
    echo "gen-v1-tls.sh: openssl command failed: $1 $2" >&2
    cat "$log" >&2
    rm -f "$log"
    exit 1
  fi
  rm -f "$log"
}

ca_fingerprint() {
  openssl x509 -in "$CA_CRT" -noout -fingerprint -sha256 | sed 's/^.*=//'
}

# ca_pair_usable reports whether both CA files exist, parse, match each other,
# and the certificate is currently valid. A partial or broken pair is never
# regenerated implicitly: that would rotate the CA behind every pinned client.
ca_pair_usable() {
  [[ -f "$CA_CRT" && -f "$CA_KEY" ]] || return 1
  openssl x509 -in "$CA_CRT" -noout >/dev/null 2>&1 || return 1
  openssl pkey -in "$CA_KEY" -noout >/dev/null 2>&1 || return 1
  local cert_pub key_pub
  cert_pub="$(openssl x509 -in "$CA_CRT" -noout -pubkey 2>/dev/null)" || return 1
  key_pub="$(openssl pkey -in "$CA_KEY" -pubout 2>/dev/null)" || return 1
  [[ "$cert_pub" == "$key_pub" ]] || return 1
  openssl x509 -in "$CA_CRT" -checkend 0 -noout >/dev/null 2>&1 || return 1
  return 0
}

# leaf_pair_usable reports whether both files of a leaf pair exist, match each
# other, and verify against the current CA. Either condition failing means the
# pair is missing or stale and must be reissued; the CA is never touched.
leaf_pair_usable() {
  local cert="$1" key="$2"
  [[ -f "$cert" && -f "$key" ]] || return 1
  openssl x509 -in "$cert" -noout >/dev/null 2>&1 || return 1
  openssl pkey -in "$key" -noout >/dev/null 2>&1 || return 1
  local cert_pub key_pub
  cert_pub="$(openssl x509 -in "$cert" -noout -pubkey 2>/dev/null)" || return 1
  key_pub="$(openssl pkey -in "$key" -pubout 2>/dev/null)" || return 1
  [[ "$cert_pub" == "$key_pub" ]] || return 1
  openssl verify -CAfile "$CA_CRT" "$cert" >/dev/null 2>&1 || return 1
  return 0
}

# leaf_names_ok verifies that a reusable leaf carries every required SAN. Both
# leaves are signed by the same CA, so a copied edge pair would otherwise pass
# the CA/key check while clients dialing auth:9091 reject the certificate.
leaf_names_ok() {
  local cert="$1"
  shift
  local san wanted
  san="$(openssl x509 -in "$cert" -noout -ext subjectAltName 2>/dev/null)" || return 1
  for wanted in "$@"; do
    grep -qF -- "$wanted" <<<"$san" || return 1
  done
  return 0
}

if [[ "$FORCE" -eq 0 ]] &&
  ca_pair_usable &&
  leaf_pair_usable "$AUTH_CRT" "$AUTH_KEY" &&
  leaf_names_ok "$AUTH_CRT" "DNS:auth" "IP Address:127.0.0.1" &&
  leaf_pair_usable "$EDGE_CRT" "$EDGE_KEY" &&
  leaf_names_ok "$EDGE_CRT" "DNS:localhost"; then
  echo "CA SHA-256 fingerprint: $(ca_fingerprint)"
  echo "reusing existing CA in $TARGET_DIR"
  echo "TLS material already present in $TARGET_DIR (use --force to regenerate)"
  exit 0
fi

old_ca_fp=""
if [[ -f "$CA_CRT" ]]; then
  old_ca_fp="$(ca_fingerprint 2>/dev/null || true)"
fi

rotate_ca=0
if [[ "$FORCE" -eq 1 ]]; then
  rotate_ca=1
elif [[ -e "$CA_CRT" || -e "$CA_KEY" ]]; then
  if ! ca_pair_usable; then
    echo "gen-v1-tls.sh: existing CA pair in $TARGET_DIR is incomplete, mismatched, or expired; rerun with --force to rotate it" >&2
    exit 1
  fi
  echo "CA SHA-256 fingerprint: $(ca_fingerprint)"
  echo "reusing existing CA in $TARGET_DIR"
else
  rotate_ca=1
fi

if [[ "$rotate_ca" -eq 1 ]]; then
  run_openssl openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout "$CA_KEY" -out "$CA_CRT" -days 3650 -sha256 \
    -subj "/CN=IBEX v1-single-node CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"

  new_ca_fp="$(ca_fingerprint)"
  echo "CA SHA-256 fingerprint: $new_ca_fp"
  if [[ -n "$old_ca_fp" && "$old_ca_fp" != "$new_ca_fp" ]]; then
    echo "WARNING: the CA was rotated; every client pinned to the previous ca.crt must install the new one" >&2
  fi
fi

issue_leaf() {
  local name="$1" san="$2" cert="$3" key="$4"
  local csr ext
  csr="$(mktemp "$TARGET_DIR/.${name}.csr.XXXXXX")"
  ext="$(mktemp "$TARGET_DIR/.${name}.ext.XXXXXX")"

  run_openssl openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout "$key" -out "$csr" -subj "/CN=$name"
  cat >"$ext" <<EOF_EXT
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
subjectAltName=$san
EOF_EXT
  run_openssl openssl x509 -req -in "$csr" -CA "$CA_CRT" -CAkey "$CA_KEY" \
    -set_serial "0x$(openssl rand -hex 16)" -days 825 -sha256 \
    -extfile "$ext" -out "$cert"
  rm -f "$csr" "$ext"
}

issue_auth=0
issue_edge=0
if [[ "$rotate_ca" -eq 1 ]]; then
  issue_auth=1
  issue_edge=1
else
  if ! leaf_pair_usable "$AUTH_CRT" "$AUTH_KEY" ||
    ! leaf_names_ok "$AUTH_CRT" "DNS:auth" "IP Address:127.0.0.1"; then
    issue_auth=1
  fi
  if ! leaf_pair_usable "$EDGE_CRT" "$EDGE_KEY" ||
    ! leaf_names_ok "$EDGE_CRT" "DNS:localhost"; then
    issue_edge=1
  fi
fi

if [[ "$issue_auth" -eq 1 ]]; then
  issue_leaf auth "DNS:auth,DNS:localhost,IP:127.0.0.1,IP:::1" "$AUTH_CRT" "$AUTH_KEY"
fi
if [[ "$issue_edge" -eq 1 ]]; then
  issue_leaf edge "DNS:localhost,DNS:console,IP:127.0.0.1" "$EDGE_CRT" "$EDGE_KEY"
fi

chmod 0600 "$CA_KEY" "$AUTH_KEY" "$EDGE_KEY"
chmod 0644 "$CA_CRT" "$AUTH_CRT" "$EDGE_CRT"

if ! openssl verify -CAfile "$CA_CRT" "$AUTH_CRT"; then
  echo "gen-v1-tls.sh: auth.crt does not verify against ca.crt" >&2
  exit 1
fi
if ! openssl verify -CAfile "$CA_CRT" "$EDGE_CRT"; then
  echo "gen-v1-tls.sh: edge.crt does not verify against ca.crt" >&2
  exit 1
fi

auth_san="$(openssl x509 -in "$AUTH_CRT" -noout -ext subjectAltName)"
if ! grep -q "DNS:auth" <<<"$auth_san"; then
  echo "gen-v1-tls.sh: auth.crt is missing the DNS:auth SAN" >&2
  exit 1
fi
if ! grep -q "IP Address:127.0.0.1" <<<"$auth_san"; then
  echo "gen-v1-tls.sh: auth.crt is missing the IP:127.0.0.1 SAN" >&2
  exit 1
fi

edge_san="$(openssl x509 -in "$EDGE_CRT" -noout -ext subjectAltName)"
if ! grep -q "DNS:localhost" <<<"$edge_san"; then
  echo "gen-v1-tls.sh: edge.crt is missing the DNS:localhost SAN" >&2
  exit 1
fi

echo "generated TLS material in $TARGET_DIR"
printf '%s\n' "$auth_san"
