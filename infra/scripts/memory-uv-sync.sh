#!/usr/bin/env bash
# Fail closed if memory locked deps cannot be synced with uv.
set -euo pipefail

MEMORY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/memory" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for memory CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$MEMORY_DIR/uv.lock" ]]; then
  echo "missing $MEMORY_DIR/uv.lock — commit the lockfile" >&2
  exit 1
fi

WHEEL_DIR="$MEMORY_DIR/.wheels"
bash "$(dirname "${BASH_SOURCE[0]}")/build-authclient-wheel.sh" "$WHEEL_DIR"

cd "$MEMORY_DIR"
uv sync --frozen --no-build --extra dev --no-install-project \
  --find-links "$WHEEL_DIR" --no-install-package authclient
uv pip install --no-index --find-links "$WHEEL_DIR" "authclient==0.1.0"
