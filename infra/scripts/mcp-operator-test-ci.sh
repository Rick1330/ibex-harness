#!/usr/bin/env bash
# Run services/mcp-operator unit tests (GAP-009 gateway surface).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MCP_DIR="$ROOT/services/mcp-operator"

if [[ ! -f "$MCP_DIR/pyproject.toml" ]]; then
  echo "services/mcp-operator not present — failing mcp-operator tests" >&2
  exit 1
fi

# W5.5 / P0-14: the shared descriptor gate (packages/mcp_tool_descriptors) is
# exercised here and only here. ci.yml invokes this script once and
# mcp-memory-test-ci.sh twice, so running the shared suite from the operator job
# keeps one invocation per CI run instead of two.
bash "$ROOT/infra/scripts/mcp-tool-descriptors-test-ci.sh"

cd "$MCP_DIR"
bash "$ROOT/infra/scripts/mcp-operator-uv-sync.sh"
.venv/bin/ruff check app tests
# W5.5 / P0-14: fail on any unrecorded change to the published MCP tool surface
# (mcp_tools.json). Validation only — the check never writes, and it runs outside
# the coverage run so the gate below measures only what the test suite exercises.
#
# P1-02: when the CI checkout knows its base branch, also diff the committed
# record against that ref, so a tool cannot be removed (or a schema silently
# rewritten) in the same commit that regenerates the record. GITHUB_BASE_REF is a
# branch name, so the checkout must fetch it first:
#   git fetch --no-tags --depth=1 origin \
#     "+refs/heads/${GITHUB_BASE_REF}:refs/remotes/origin/${GITHUB_BASE_REF}"
# Without it the comparison cannot run, and the script warns instead of failing a
# checkout for a ref it was never given.
BASE_REF="${IBEX_MCP_DESCRIPTOR_BASE_REF:-}"
if [[ -z "$BASE_REF" && -n "${GITHUB_BASE_REF:-}" ]]; then
  if git -C "$ROOT" rev-parse --verify --quiet "origin/${GITHUB_BASE_REF}^{commit}" >/dev/null; then
    BASE_REF="origin/${GITHUB_BASE_REF}"
  elif git -C "$ROOT" rev-parse --verify --quiet "${GITHUB_BASE_REF}^{commit}" >/dev/null; then
    BASE_REF="${GITHUB_BASE_REF}"
  else
    echo "warning: GITHUB_BASE_REF='${GITHUB_BASE_REF}' is not fetched; skipping the descriptor base-ref diff." >&2
    echo "warning: the CI checkout must run: git fetch --no-tags --depth=1 origin \"+refs/heads/${GITHUB_BASE_REF}:refs/remotes/origin/${GITHUB_BASE_REF}\"" >&2
  fi
fi
# The descriptor gate reads two records outside this service: the committed
# record's deprecation notice at engineering/architecture-v2/contracts/
# deprecations.json, and the same record at BASE_REF. The CLI confines every
# path it reads to --allow-root (default: the working directory), so the gate
# declares the repository root as its read scope. This is a scope declaration,
# not a bypass: the record path is still confined, still validated, and still
# compared against BASE_REF.
if [[ -n "$BASE_REF" ]]; then
  .venv/bin/python -m app.descriptors --allow-root "$ROOT" --check-base "$BASE_REF"
else
  .venv/bin/python -m app.descriptors --allow-root "$ROOT" --check
fi
.venv/bin/pytest -q \
  -m "not integration" \
  --cov=app \
  --cov-report=xml:coverage-mcp-operator.xml \
  --cov-report=term-missing \
  --cov-fail-under=90
