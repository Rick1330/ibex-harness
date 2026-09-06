#!/usr/bin/env bash
# Generate Python protobuf stubs for context gRPC (m3.5.C.6).
# Output lives under packages/proto/gen/ (gitignored); required at test/runtime.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROTO_DIR="$ROOT/packages/proto"
GEN_PY="$PROTO_DIR/gen/python"
MARKER="$GEN_PY/ibex/context/v1/context_pb2.py"

if [[ -f "$MARKER" ]]; then
  echo "context protobuf stubs already present"
  exit 0
fi

_verify_sha256() {
  local expected="$1"
  local file="$2"
  if command -v sha256sum >/dev/null 2>&1; then
    echo "${expected}  ${file}" | sha256sum -c -
  elif command -v shasum >/dev/null 2>&1; then
    echo "${expected}  ${file}" | shasum -a 256 -c -
  else
    echo "neither sha256sum nor shasum found" >&2
    exit 1
  fi
}

if ! command -v buf >/dev/null 2>&1; then
  # Auto-install only the pinned version; checksums come from that release's sha256.txt.
  BUF_VERSION="${BUF_VERSION:-1.47.2}"
  PINNED_BUF_VERSION="1.47.2"
  if [[ "${BUF_VERSION}" != "${PINNED_BUF_VERSION}" ]]; then
    echo "auto-install supports Buf ${PINNED_BUF_VERSION} only; install ${BUF_VERSION} manually" >&2
    exit 1
  fi
  ARTIFACT="buf-$(uname -s)-$(uname -m)"
  BASE_URL="https://github.com/bufbuild/buf/releases/download/v${BUF_VERSION}"
  echo "buf not found — installing Buf CLI ${BUF_VERSION} to \$HOME/.local/bin"
  mkdir -p "$HOME/.local/bin"
  TMP="$(mktemp)"
  SUMS="$(mktemp)"
  # Fail closed on HTTP errors; do not follow redirects off HTTPS.
  curl --proto '=https' --tlsv1.2 -fsSL "${BASE_URL}/sha256.txt" -o "$SUMS"
  curl --proto '=https' --tlsv1.2 -fsSL "${BASE_URL}/${ARTIFACT}" -o "$TMP"
  BUF_SHA256="$(awk -v artifact="${ARTIFACT}" '$2 == artifact { print $1; exit }' "$SUMS")"
  if [[ -z "${BUF_SHA256}" ]]; then
    echo "no checksum for ${ARTIFACT} in Buf ${BUF_VERSION} sha256.txt" >&2
    rm -f "$TMP" "$SUMS"
    exit 1
  fi
  _verify_sha256 "${BUF_SHA256}" "${TMP}"
  install -m 0755 "$TMP" "$HOME/.local/bin/buf"
  rm -f "$TMP" "$SUMS"
  export PATH="$HOME/.local/bin:$PATH"
fi

cd "$PROTO_DIR"
buf generate
if [[ ! -f "$MARKER" ]]; then
  echo "expected generated stub missing: $MARKER" >&2
  exit 1
fi
echo "generated $MARKER"
