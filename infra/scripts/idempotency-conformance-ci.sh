#!/usr/bin/env bash
# Run the request-idempotency-core.v1 cross-runtime conformance suite.
# Requires a migrated PostgreSQL (CI applies migrations before invoking this).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUITE_DIR="$ROOT/infra/tests/idempotency-conformance"

if [[ ! -f "$SUITE_DIR/pyproject.toml" ]]; then
  echo "idempotency conformance suite not present — skipping"
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for the conformance suite (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi

CANONICAL_DSN="${IBEX_IDEMPOTENCY_CONFORMANCE_DSN:-${POSTGRES_TEST_DSN:-}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "IBEX_IDEMPOTENCY_CONFORMANCE_DSN or POSTGRES_TEST_DSN required" >&2
  exit 1
fi
export IBEX_IDEMPOTENCY_CONFORMANCE_DSN="${CANONICAL_DSN}"

cd "$SUITE_DIR"
uv sync --frozen --extra dev
.venv/bin/ruff check tests
.venv/bin/pytest -q
