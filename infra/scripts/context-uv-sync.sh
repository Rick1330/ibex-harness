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
# Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
# --no-install-project: tests import via pyproject pythonpath=["."].
uv sync --frozen --no-build --extra dev --no-install-project
