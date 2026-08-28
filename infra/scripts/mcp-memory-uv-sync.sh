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

cd "$MCP_DIR"
uv sync --frozen --extra dev --no-install-project
