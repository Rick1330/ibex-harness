#!/usr/bin/env bash
# Build a wheel for packages/apierror_py (trusted monorepo source only).
# Usage: build-apierror-py-wheel.sh <output-dir>
set -euo pipefail

OUT_DIR="${1:?output directory required}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG_DIR="$ROOT/packages/apierror_py"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$PKG_DIR/pyproject.toml" ]]; then
  echo "missing $PKG_DIR/pyproject.toml" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
uv build --wheel --out-dir "$OUT_DIR" "$PKG_DIR"
