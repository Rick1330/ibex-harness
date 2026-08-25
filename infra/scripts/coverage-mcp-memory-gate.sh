#!/usr/bin/env bash
# Fail if services/mcp-memory app coverage is below MIN_COVERAGE (default 90).
# Regenerates coverage when the XML report is missing or older than sources.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIN_RAW="${MIN_COVERAGE:-90}"
if ! [[ "$MIN_RAW" =~ ^[0-9]+$ ]] || (( MIN_RAW > 100 )); then
  echo "MIN_COVERAGE must be an integer 0-100, got: $MIN_RAW"
  exit 1
fi

MCP_DIR="$ROOT/services/mcp-memory"
if [[ ! -f "$MCP_DIR/pyproject.toml" ]]; then
  echo "services/mcp-memory not present — skipping mcp-memory coverage gate"
  exit 0
fi

cd "$MCP_DIR"

report_stale() {
  local report="$1"
  if [[ ! -f "$report" ]]; then
    return 0
  fi
  # Newer sources than the report → regenerate.
  if find app tests pyproject.toml -type f -newer "$report" 2>/dev/null | grep -q .; then
    return 0
  fi
  return 1
}

if report_stale coverage-mcp-memory.xml; then
  bash "$ROOT/infra/scripts/mcp-memory-uv-sync.sh"
  .venv/bin/pytest -q \
    --cov=app \
    --cov-report=xml:coverage-mcp-memory.xml \
    --cov-report=term-missing \
    --cov-fail-under="$MIN_RAW"
fi

.venv/bin/python - <<PY
import os
import sys
import xml.etree.ElementTree as ET

min_pct = float(os.environ.get("MIN_COVERAGE", "90"))
root = ET.parse("coverage-mcp-memory.xml").getroot()
rate = float(root.get("line-rate", "0")) * 100.0
if rate + 1e-9 < min_pct:
    print(f"mcp-memory coverage {rate:.2f}% below minimum {min_pct:.0f}%", file=sys.stderr)
    sys.exit(1)
print(f"mcp-memory app coverage gate passed ({rate:.2f}% >= {min_pct:.0f}%)")
PY
