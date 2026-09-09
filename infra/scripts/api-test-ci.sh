#!/usr/bin/env bash
# Run services/api unit tests (m4.A.1+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="$ROOT/services/api"

if [[ ! -f "$API_DIR/pyproject.toml" ]]; then
  echo "services/api not present — skipping api tests"
  exit 0
fi

cd "$API_DIR"
bash "$ROOT/infra/scripts/api-uv-sync.sh"
.venv/bin/ruff check app tests
.venv/bin/pytest -q \
  -m "not integration" \
  --cov=app \
  --cov-report=xml:coverage-api.xml \
  --cov-report=term-missing \
  --cov-fail-under=95
