#!/usr/bin/env bash
# Fail closed if api locked deps cannot be synced with uv.
set -euo pipefail

API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../services/api" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for api CI (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi
if [[ ! -f "$API_DIR/uv.lock" ]]; then
  echo "missing $API_DIR/uv.lock — commit the lockfile" >&2
  exit 1
fi

WHEEL_DIR="$API_DIR/.wheels"
bash "$(dirname "${BASH_SOURCE[0]}")/build-authclient-wheel.sh" "$WHEEL_DIR"
bash "$(dirname "${BASH_SOURCE[0]}")/build-ibex-async-db-wheel.sh" "$WHEEL_DIR"
bash "$(dirname "${BASH_SOURCE[0]}")/build-apierror-py-wheel.sh" "$WHEEL_DIR"

cd "$API_DIR"
uv sync --frozen --no-build --extra dev --no-install-project \
  --find-links "$WHEEL_DIR" \
  --no-install-package authclient \
  --no-install-package ibex-async-db \
  --no-install-package apierror-py
# Same version can gain modules (e.g. validate.py); bust uv cache so CI
# does not install a stale wheel content hash for the pinned version.
uv pip install --no-cache --force-reinstall --no-index --find-links "$WHEEL_DIR" \
  "authclient==0.1.3" "ibex-async-db==0.1.0" "apierror-py==0.1.0"
