#!/usr/bin/env bash
# Run packages/mcp_tool_descriptors unit tests (W5.5 / P0-14 contract gate).
#
# Invoked from infra/scripts/mcp-operator-test-ci.sh only: that is the single
# place ci.yml runs it, so the shared suite runs once per CI run rather than in
# both MCP service jobs (mcp-memory-test-ci.sh is invoked twice in ci.yml).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG_DIR="$ROOT/packages/mcp_tool_descriptors"

if [[ ! -f "$PKG_DIR/pyproject.toml" ]]; then
  echo "packages/mcp_tool_descriptors not present — failing mcp_tool_descriptors tests" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for mcp_tool_descriptors CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi

cd "$PKG_DIR"
uv sync --frozen --extra dev  # NOSONAR shell:S8541
.venv/bin/ruff check src tests
# The package has no service to measure, so its own suite carries the coverage
# gate; the service gates keep measuring `--cov=app` only.
.venv/bin/pytest -q \
  --cov=src/mcp_tool_descriptors \
  --cov-report=term-missing \
  --cov-fail-under=90
