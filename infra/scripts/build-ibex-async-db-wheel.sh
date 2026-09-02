#!/usr/bin/env bash
# Build a wheel for packages/ibex_async_db (trusted monorepo source only).
# Usage: build-ibex-async-db-wheel.sh <output-dir>
set -euo pipefail

OUT_DIR="${1:?output directory required}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE_DIR="$ROOT/packages/ibex_async_db"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$PACKAGE_DIR/pyproject.toml" ]]; then
  echo "missing $PACKAGE_DIR/pyproject.toml" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
uv build --wheel --out-dir "$OUT_DIR" "$PACKAGE_DIR"
