#!/usr/bin/env bash
# Run services/memory PgVectorStore integration tests (requires migrated pgvector Postgres).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MEMORY_DIR="$ROOT/services/memory"

if [[ ! -f "$MEMORY_DIR/pyproject.toml" ]]; then
  echo "services/memory not present — skipping memory integration tests"
  exit 0
fi

# One canonical DSN for migrate + pytest (prefer explicit migrate/app URLs).
CANONICAL_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-${IBEX_MEMORY_DATABASE_URL:-}}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "POSTGRES_DSN, POSTGRES_TEST_DSN, or IBEX_MEMORY_DATABASE_URL required" >&2
  exit 1
fi

export POSTGRES_DSN="${CANONICAL_DSN}"
export POSTGRES_MIGRATE_DSN="${CANONICAL_DSN}"
export POSTGRES_TEST_DSN="${CANONICAL_DSN}"
export IBEX_MEMORY_DATABASE_URL="${CANONICAL_DSN}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up

cd "$MEMORY_DIR"
bash "$ROOT/infra/scripts/memory-uv-sync.sh"
.venv/bin/pytest -q -m "integration and not security_integration"
