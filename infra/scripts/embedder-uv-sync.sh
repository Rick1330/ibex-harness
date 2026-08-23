#!/usr/bin/env bash
# Sync services/embedder deps from uv.lock without running third-party setup scripts.
set -euo pipefail

EMBEDDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/embedder" && pwd)"
cd "$EMBEDDER_DIR"

if ! command -v uv >/dev/null 2>&1 || [[ ! -f uv.lock ]]; then
  echo "uv and services/embedder/uv.lock are required" >&2
  exit 1
fi

# Locked dependencies: wheels only (--no-build blocks sdist setup.py execution).
uv sync --frozen --no-build --extra dev --no-install-project
# First-party package: editable install from repo-controlled pyproject.toml only.
uv pip install --no-deps -e .
