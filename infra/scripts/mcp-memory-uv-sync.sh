#!/usr/bin/env bash
# Fail closed if mcp-memory locked deps cannot be synced with uv.
set -euo pipefail

MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/mcp-memory" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for mcp-memory CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$MCP_DIR/uv.lock" ]]; then
  echo "missing $MCP_DIR/uv.lock — commit the lockfile" >&2
  exit 1
fi

WHEEL_DIR="$MCP_DIR/.wheels"
bash "$(dirname "${BASH_SOURCE[0]}")/build-authclient-wheel.sh" "$WHEEL_DIR"
AUTHCLIENT_WHEEL="$(find "$WHEEL_DIR" -maxdepth 1 -name 'authclient-*.whl' -print -quit)"
if [[ -z "$AUTHCLIENT_WHEEL" ]]; then
  echo "missing authclient wheel in $WHEEL_DIR" >&2
  exit 1
fi

cd "$MCP_DIR"
uv sync --frozen --no-build --extra dev --no-install-project \
  --find-links "$WHEEL_DIR" --no-install-package authclient
uv pip install --no-index "$AUTHCLIENT_WHEEL"
