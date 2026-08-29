#!/usr/bin/env bash
# Run memory security integration tests (m3.E.1 ISO-* suite).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MEMORY_DIR="$ROOT/services/memory"

if [[ ! -f "$MEMORY_DIR/pyproject.toml" ]]; then
  echo "services/memory not present — skipping memory security integration tests"
  exit 0
fi

CANONICAL_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-${IBEX_MEMORY_DATABASE_URL:-}}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "POSTGRES_DSN, POSTGRES_TEST_DSN, or IBEX_MEMORY_DATABASE_URL required" >&2
  exit 1
fi
if [[ -z "${REDIS_URL:-}" ]]; then
  echo "REDIS_URL required for memory security integration tests" >&2
  exit 1
fi

export POSTGRES_DSN="${CANONICAL_DSN}"
export POSTGRES_MIGRATE_DSN="${CANONICAL_DSN}"
export POSTGRES_TEST_DSN="${CANONICAL_DSN}"
export IBEX_MEMORY_DATABASE_URL="${IBEX_MEMORY_DATABASE_URL:-${CANONICAL_DSN}}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up

cd "$MEMORY_DIR"
bash "$ROOT/infra/scripts/memory-uv-sync.sh"

count=$(.venv/bin/pytest -q -m security_integration --collect-only 2>/dev/null \
  | grep -c '^tests/integration/security/.*::test_memory_iso_' || true)
if [[ "${count}" -lt 12 ]]; then
  echo "expected at least 12 test_memory_iso_* tests, found ${count}" >&2
  exit 1
fi

.venv/bin/pytest -q -m security_integration
