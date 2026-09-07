#!/usr/bin/env bash
# MCP stub protocol conformance evidence for Phase 2.5 exit criterion #7 /
# Phase 3.5.E.1 conformance deepening.
#
# Runs the mcp-memory HTTP handshake suite (initialize → tools/list → tools/call)
# for both explicitly supported protocol versions (2024-11-05 and 2025-11-25),
# plus bearer auth, protected-resource metadata (RFC 9728 minimum fields), and
# fail-closed-on-auth-outage. Live Auth gRPC is covered by make e2e-phase25;
# this script is the offline/CI-safe conformance evidence.
#
# Optional: IBEX_MCP_INSPECTOR=1 attempts `npx @modelcontextprotocol/inspector`
# against a running server (not required for exit; documented for operators).
# Official @modelcontextprotocol/conformance harness adoption is deferred
# (tracked as an E.1 follow-up issue).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR/services/mcp-memory"

echo "=== MCP conformance (HTTP stub suite + dual protocol versions) ==="

if [[ ! -d .venv ]]; then
  # Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
  uv sync --frozen --no-build --extra dev >/dev/null
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pytest -q \
  tests/test_http.py::test_mcp_initialize_negotiates_protocol_version \
  tests/test_http.py::test_mcp_initialize_and_tools_list \
  tests/test_http.py::test_mcp_requires_bearer \
  tests/test_http.py::test_protected_resource_metadata \
  tests/test_http.py::test_build_protected_resource_metadata_helper \
  tests/test_http.py::test_auth_unavailable_fail_closed \
  tests/test_http.py::test_metrics_endpoint \
  tests/test_http.py::test_supported_protocol_versions_constant

echo "PASS: MCP Streamable HTTP stub conformance suite (2024-11-05 + 2025-11-25)"

if [[ "${IBEX_MCP_INSPECTOR:-0}" == "1" ]]; then
  MCP_URL="${IBEX_MCP_ADDR:-http://127.0.0.1:8090}/mcp"
  echo "IBEX_MCP_INSPECTOR=1: launching inspector against $MCP_URL (manual)"
  npx --yes @modelcontextprotocol/inspector "$MCP_URL" || {
    echo "WARN: inspector failed or not installed; suite above remains the gate evidence"
  }
fi

echo "mcp-conformance passed"
