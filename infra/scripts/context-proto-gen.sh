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

if ! command -v buf >/dev/null 2>&1; then
  BUF_VERSION="${BUF_VERSION:-1.47.2}"
  # Pin checksums for the official GitHub release binaries (v1.47.2 sha256.txt).
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) BUF_SHA256="9043df6e64c012d0e4165a1f8eff3cd87e858435c04c10731be2a4cd3cd6e016" ;;
    Darwin-x86_64) BUF_SHA256="84b964979a73ac3db2a6e18ef9f685628ace60f63b3d1d8b1b39f4ea66fc18fe" ;;
    Linux-aarch64) BUF_SHA256="47ddd7ac0bb2a29f8c92aa420dd113bed3b6857190976402eec93ab9847270b4" ;;
    Linux-x86_64) BUF_SHA256="3a0c4da8d46eea8136affa63db202c76a44f8112384160b73c3fffb1cf14b5d8" ;;
    *)
      echo "unsupported platform for auto-install of buf; install Buf ${BUF_VERSION} manually" >&2
      exit 1
      ;;
  esac
  ARTIFACT="buf-$(uname -s)-$(uname -m)"
  URL="https://github.com/bufbuild/buf/releases/download/v${BUF_VERSION}/${ARTIFACT}"
  echo "buf not found — installing Buf CLI ${BUF_VERSION} to \$HOME/.local/bin"
  mkdir -p "$HOME/.local/bin"
  TMP="$(mktemp)"
  # Fail closed on HTTP errors; do not follow redirects off HTTPS.
  curl --proto '=https' --tlsv1.2 -fsSL "$URL" -o "$TMP"
  echo "${BUF_SHA256}  ${TMP}" | sha256sum -c -
  install -m 0755 "$TMP" "$HOME/.local/bin/buf"
  rm -f "$TMP"
  export PATH="$HOME/.local/bin:$PATH"
fi

cd "$PROTO_DIR"
buf generate
test -f "$MARKER"
echo "generated $MARKER"
