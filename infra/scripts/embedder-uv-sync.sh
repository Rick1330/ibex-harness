#!/usr/bin/env bash
# Sync services/embedder locked deps from uv.lock without running setup scripts.
set -euo pipefail

EMBEDDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/embedder" && pwd)"
cd "$EMBEDDER_DIR"

if ! command -v uv >/dev/null 2>&1 || [[ ! -f uv.lock ]]; then
  echo "uv and services/embedder/uv.lock are required" >&2
  exit 1
fi

# Wheels only: --no-build blocks third-party sdist setup.py execution (Sonar S8541).
uv sync --frozen --no-build --extra dev --no-install-project
