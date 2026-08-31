#!/usr/bin/env bash
# Run services/worker unit tests (m3.5.A.1+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKER_DIR="$ROOT/services/worker"

if [[ ! -f "$WORKER_DIR/pyproject.toml" ]]; then
  echo "services/worker not present — skipping worker tests"
  exit 0
fi

cd "$WORKER_DIR"
bash "$ROOT/infra/scripts/worker-uv-sync.sh"
.venv/bin/ruff check app tests
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
.venv/bin/pytest -q \
  -m "not integration" \
  --cov=app \
  --cov-report=xml:coverage-worker.xml \
  --cov-report=term-missing \
  --cov-fail-under=90
