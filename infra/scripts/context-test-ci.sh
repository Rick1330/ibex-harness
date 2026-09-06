#!/usr/bin/env bash
# Run services/context unit tests (m3.5.C.1+).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTEXT_DIR="$ROOT/services/context"
PROTO_PY="$ROOT/packages/proto/gen/python"

if [[ ! -f "$CONTEXT_DIR/pyproject.toml" ]]; then
  echo "services/context not present — context tests required in CI" >&2
  exit 1
fi

cd "$CONTEXT_DIR"
bash "$ROOT/infra/scripts/context-uv-sync.sh"
bash "$ROOT/infra/scripts/context-proto-gen.sh"
export PYTHONPATH="${PROTO_PY}${PYTHONPATH:+:$PYTHONPATH}"
.venv/bin/ruff check app tests
.venv/bin/pytest -q \
  --cov=app \
  --cov-report=xml:coverage-context.xml \
  --cov-report=term-missing \
  --cov-fail-under=95
