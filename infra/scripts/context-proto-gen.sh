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
  echo "buf not found — installing Buf CLI ${BUF_VERSION} to \$HOME/.local/bin"
  mkdir -p "$HOME/.local/bin"
  curl -sSL \
    "https://github.com/bufbuild/buf/releases/download/v${BUF_VERSION}/buf-$(uname -s)-$(uname -m)" \
    -o "$HOME/.local/bin/buf"
  chmod +x "$HOME/.local/bin/buf"
  export PATH="$HOME/.local/bin:$PATH"
fi

cd "$PROTO_DIR"
buf generate
test -f "$MARKER"
echo "generated $MARKER"
