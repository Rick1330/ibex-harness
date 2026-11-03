#!/usr/bin/env bash
# Run services/mcp-operator unit tests (GAP-009 gateway surface).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MCP_DIR="$ROOT/services/mcp-operator"

if [[ ! -f "$MCP_DIR/pyproject.toml" ]]; then
  echo "services/mcp-operator not present — failing mcp-operator tests" >&2
  exit 1
fi

cd "$MCP_DIR"
bash "$ROOT/infra/scripts/mcp-operator-uv-sync.sh"
.venv/bin/ruff check app tests
.venv/bin/pytest -q \
  -m "not integration" \
  --cov=app \
  --cov-report=xml:coverage-mcp-operator.xml \
  --cov-report=term-missing \
  --cov-fail-under=90
