#!/usr/bin/env bash
# Run packages/authclient unit tests (shared AuthService codec + dial client).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG_DIR="$ROOT/packages/authclient"

if [[ ! -f "$PKG_DIR/pyproject.toml" ]]; then
  echo "packages/authclient not present — failing authclient tests" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for authclient CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi

cd "$PKG_DIR"
# The dev dependency group pins grpcio, so the channel tests run without an
# undeclared ad-hoc `--extra grpc --with pytest` invocation.
uv sync --frozen
.venv/bin/ruff check src tests
.venv/bin/pytest -q tests
