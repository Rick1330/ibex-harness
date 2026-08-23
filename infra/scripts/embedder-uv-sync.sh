#!/usr/bin/env bash
# Fail closed if embedder locked deps cannot be synced with uv.
set -euo pipefail

EMBEDDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/embedder" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for embedder CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$EMBEDDER_DIR/uv.lock" ]]; then
  echo "missing $EMBEDDER_DIR/uv.lock — commit the lockfile" >&2
  exit 1
fi

cd "$EMBEDDER_DIR"
# Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
uv sync --frozen --no-build --extra dev --no-install-project
