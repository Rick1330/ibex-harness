#!/usr/bin/env bash
# Run services/memory unit tests (m3.2.1+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MEMORY_DIR="$ROOT/services/memory"

if [[ ! -f "$MEMORY_DIR/pyproject.toml" ]]; then
  echo "services/memory not present — skipping memory tests"
  exit 0
fi

cd "$MEMORY_DIR"
bash "$ROOT/infra/scripts/memory-uv-sync.sh"
.venv/bin/ruff check app tests
.venv/bin/pytest -q \
  --cov=app \
  --cov-report=xml:coverage-memory.xml \
  --cov-report=term-missing \
  --cov-fail-under=90
