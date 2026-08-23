#!/usr/bin/env bash
# Run services/embedder unit tests when the Python service is present (G4.M1+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EMBEDDER_DIR="$ROOT/services/embedder"

if [[ ! -f "$EMBEDDER_DIR/pyproject.toml" ]]; then
  echo "services/embedder not present — skipping embedder tests"
  exit 0
fi

cd "$EMBEDDER_DIR"

if command -v uv >/dev/null 2>&1 && [[ -f uv.lock ]]; then
  uv sync --frozen --extra dev
  uv run ruff check app tests
  uv run pytest -q \
    --cov=app \
    --cov-report=xml:coverage-embedder.xml \
    --cov-report=term-missing
else
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  .venv/bin/pip install --disable-pip-version-check --no-cache-dir -q -e ".[dev]"
  .venv/bin/ruff check app tests
  .venv/bin/pytest -q \
    --cov=app \
    --cov-report=xml:coverage-embedder.xml \
    --cov-report=term-missing
fi
