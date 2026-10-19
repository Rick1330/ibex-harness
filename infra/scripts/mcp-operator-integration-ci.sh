#!/usr/bin/env bash
# Run services/mcp-operator integration tests against a live, migrated PostgreSQL
# (RLS + explicit org filtering + cross-tenant not_found). A missing DSN is a hard
# failure in CI — a silent skip would remove the GAP-009 isolation evidence gate.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MCP_DIR="$ROOT/services/mcp-operator"

if [[ ! -f "$MCP_DIR/pyproject.toml" ]]; then
  echo "services/mcp-operator not present — skipping mcp-operator integration tests"
  exit 0
fi

DSN="${IBEX_MCP_OPERATOR_TEST_DATABASE_URL:-${POSTGRES_TEST_DSN:-}}"
if [[ -z "$DSN" ]]; then
  echo "IBEX_MCP_OPERATOR_TEST_DATABASE_URL or POSTGRES_TEST_DSN required" >&2
  exit 1
fi
export IBEX_MCP_OPERATOR_TEST_DATABASE_URL="$DSN"

cd "$MCP_DIR"
bash "$ROOT/infra/scripts/mcp-operator-uv-sync.sh"
.venv/bin/pytest -q -m integration
