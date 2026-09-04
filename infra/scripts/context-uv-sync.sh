#!/usr/bin/env bash
# Fail closed if services/context locked deps cannot be synced with uv.
set -euo pipefail

CONTEXT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/context" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for context CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$CONTEXT_DIR/uv.lock" ]]; then
  echo "missing $CONTEXT_DIR/uv.lock — commit the lockfile" >&2
  exit 1
fi

cd "$CONTEXT_DIR"
uv sync --frozen --extra dev
