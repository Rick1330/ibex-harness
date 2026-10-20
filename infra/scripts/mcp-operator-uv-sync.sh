#!/usr/bin/env bash
# Fail closed if services/mcp-operator locked deps cannot be synced with uv.
# First-party path packages are built as local wheels; no untrusted sdist runs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MCP_DIR="$ROOT/services/mcp-operator"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for mcp-operator CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$MCP_DIR/uv.lock" ]]; then
  echo "missing $MCP_DIR/uv.lock — commit the lockfile" >&2
  exit 1
fi

WHEEL_DIR="$MCP_DIR/.wheels"
rm -rf "$WHEEL_DIR"
mkdir -p "$WHEEL_DIR"
bash "$ROOT/infra/scripts/build-authclient-wheel.sh" "$WHEEL_DIR"
bash "$ROOT/infra/scripts/build-mcp-gateway-wheel.sh" "$WHEEL_DIR"
bash "$ROOT/infra/scripts/build-ibex-async-db-wheel.sh" "$WHEEL_DIR"

cd "$MCP_DIR"
uv sync --frozen --no-build --extra dev --no-install-project \
  --find-links "$WHEEL_DIR" \
  --no-install-package authclient \
  --no-install-package mcp-gateway \
  --no-install-package ibex-async-db
uv pip install --no-cache --force-reinstall --no-index --no-deps \
  "$WHEEL_DIR"/authclient-*.whl \
  "$WHEEL_DIR"/mcp_gateway-*.whl \
  "$WHEEL_DIR"/ibex_async_db-*.whl
