#!/usr/bin/env bash
# Fail closed if worker locked deps cannot be synced with uv.
set -euo pipefail

WORKER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/worker" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for worker CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$WORKER_DIR/uv.lock" ]]; then
  echo "missing $WORKER_DIR/uv.lock — commit the lockfile" >&2
  exit 1
fi

WHEEL_DIR="$WORKER_DIR/.wheels"
bash "$(dirname "${BASH_SOURCE[0]}")/build-ibex-async-db-wheel.sh" "$WHEEL_DIR"

cd "$WORKER_DIR"
uv sync --frozen --no-build --extra dev --no-install-project \
  --find-links "$WHEEL_DIR" --no-install-package ibex-async-db
uv pip install --no-index --find-links "$WHEEL_DIR" "ibex-async-db==0.1.0"
