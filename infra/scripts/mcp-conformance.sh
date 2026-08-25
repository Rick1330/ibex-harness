#!/usr/bin/env bash
# MCP stub protocol conformance evidence for Phase 2.5 exit criterion #7.
#
# Runs the mcp-memory HTTP handshake suite (initialize → tools/list → tools/call)
# which exercises Streamable HTTP against stub handlers. Live Auth gRPC is covered
# by make e2e-phase25; this script is the offline/CI-safe conformance evidence.
#
# Optional: IBEX_MCP_INSPECTOR=1 attempts `npx @modelcontextprotocol/inspector`
# against a running server (not required for exit; documented for operators).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR/services/mcp-memory"

echo "=== MCP conformance (HTTP stub suite) ==="

if [[ ! -d .venv ]]; then
  uv sync --frozen --extra dev >/dev/null 2>&1 || uv sync --extra dev
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pytest -q tests/test_http.py::test_mcp_initialize_and_tools_list \
  tests/test_http.py::test_mcp_requires_bearer \
  tests/test_http.py::test_protected_resource_metadata \
  tests/test_http.py::test_auth_unavailable_fail_closed \
  tests/test_http.py::test_metrics_endpoint

echo "PASS: MCP Streamable HTTP stub conformance suite"

if [[ "${IBEX_MCP_INSPECTOR:-0}" == "1" ]]; then
  MCP_URL="${IBEX_MCP_ADDR:-http://127.0.0.1:8090}/mcp"
  echo "IBEX_MCP_INSPECTOR=1: launching inspector against $MCP_URL (manual)"
  npx --yes @modelcontextprotocol/inspector "$MCP_URL" || {
    echo "WARN: inspector failed or not installed; suite above remains the gate evidence"
  }
fi

echo "mcp-conformance passed"
