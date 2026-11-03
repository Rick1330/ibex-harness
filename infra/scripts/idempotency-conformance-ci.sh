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

# This script only runs where a migrated DSN is provided, so treat a missing
# DSN or an unreachable database as a hard failure: a silent skip would remove
# the GAP-001 evidence gate.
export IBEX_IDEMPOTENCY_CONFORMANCE_REQUIRED=1

cd "$SUITE_DIR"
# The only source builds here are the first-party path wheels (ibex-async-db,
# ibex-idempotency); every third-party dependency is resolved from the frozen
# lockfile, so no untrusted setup script runs.
uv sync --frozen --extra dev  # NOSONAR shell:S8541
.venv/bin/ruff check tests
.venv/bin/pytest -q

# The shared ledger adapter's unit tests ship with the package; the conformance
# suite's `testpaths` only sees its own tests/ directory, so run them here to
# keep them in CI.
cd "$ROOT/packages/ibex_idempotency"
uv sync --frozen --extra dev  # NOSONAR shell:S8541
.venv/bin/ruff check src tests
.venv/bin/pytest -q
