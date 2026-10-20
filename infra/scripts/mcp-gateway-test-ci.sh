#!/usr/bin/env bash
# Run packages/mcp_gateway unit tests (GAP-009 enforcement core).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG_DIR="$ROOT/packages/mcp_gateway"

if [[ ! -f "$PKG_DIR/pyproject.toml" ]]; then
  echo "packages/mcp_gateway not present — failing mcp_gateway tests" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for mcp_gateway CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi

cd "$PKG_DIR"
# Only first-party path wheels (authclient, mcp-gateway) are built here.
uv sync --frozen --extra dev  # NOSONAR shell:S8541
.venv/bin/ruff check src tests
.venv/bin/pytest -q
