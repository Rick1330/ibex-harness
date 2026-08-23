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

if command -v uv >/dev/null 2>&1 && [[ -f uv.lock ]]; then
  uv sync --frozen --extra dev
  uv run pytest -q --cov=app --cov-report=term-missing --cov-fail-under="$MIN_RAW"
else
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  .venv/bin/pip install --disable-pip-version-check --no-cache-dir -q -e ".[dev]"
  .venv/bin/pytest -q --cov=app --cov-report=term-missing --cov-fail-under="$MIN_RAW"
fi

echo "embedder app coverage gate passed (minimum ${MIN_RAW}%)"
