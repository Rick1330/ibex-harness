#!/usr/bin/env bash
# Run services/mcp-memory unit tests (G6.M1+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MCP_DIR="$ROOT/services/mcp-memory"

if [[ ! -f "$MCP_DIR/pyproject.toml" ]]; then
  echo "services/mcp-memory not present — skipping mcp-memory tests"
  exit 0
fi

cd "$MCP_DIR"
bash "$ROOT/infra/scripts/mcp-memory-uv-sync.sh"
.venv/bin/ruff check app tests
.venv/bin/pytest -q \
  --cov=app \
  --cov-report=xml:coverage-mcp-memory.xml \
  --cov-report=term-missing \
  --cov-fail-under=90
