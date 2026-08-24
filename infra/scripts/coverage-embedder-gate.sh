#!/usr/bin/env bash
# Fail if services/embedder app coverage is below MIN_COVERAGE (default 95).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIN_RAW="${MIN_COVERAGE:-95}"
if ! [[ "$MIN_RAW" =~ ^[0-9]+$ ]] || (( MIN_RAW > 100 )); then
  echo "MIN_COVERAGE must be an integer 0-100, got: $MIN_RAW"
  exit 1
fi

EMBEDDER_DIR="$ROOT/services/embedder"
if [[ ! -f "$EMBEDDER_DIR/pyproject.toml" ]]; then
  echo "services/embedder not present — skipping embedder coverage gate"
  exit 0
fi

cd "$EMBEDDER_DIR"

if [[ -f coverage-embedder.xml ]]; then
  .venv/bin/python - <<PY
import os
import sys
import xml.etree.ElementTree as ET

min_pct = float(os.environ.get("MIN_COVERAGE", "95"))
root = ET.parse("coverage-embedder.xml").getroot()
rate = float(root.get("line-rate", "0")) * 100.0
if rate + 1e-9 < min_pct:
    print(f"embedder coverage {rate:.2f}% below minimum {min_pct:.0f}%", file=sys.stderr)
    sys.exit(1)
print(f"embedder app coverage gate passed ({rate:.2f}% >= {min_pct:.0f}%)")
PY
  exit 0
fi

bash "$ROOT/infra/scripts/embedder-uv-sync.sh"
.venv/bin/pytest -q --cov=app --cov-report=term-missing --cov-fail-under="$MIN_RAW"
echo "embedder app coverage gate passed (minimum ${MIN_RAW}%)"
