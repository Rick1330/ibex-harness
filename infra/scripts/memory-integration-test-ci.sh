#!/usr/bin/env bash
# Run services/memory PgVectorStore integration tests (requires migrated pgvector Postgres).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MEMORY_DIR="$ROOT/services/memory"

if [[ ! -f "$MEMORY_DIR/pyproject.toml" ]]; then
  echo "services/memory not present — skipping memory integration tests"
  exit 0
fi

if [[ -z "${POSTGRES_TEST_DSN:-}" && -z "${IBEX_MEMORY_DATABASE_URL:-}" ]]; then
  echo "POSTGRES_TEST_DSN or IBEX_MEMORY_DATABASE_URL required for memory integration tests" >&2
  exit 1
fi

export POSTGRES_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-}}"
export POSTGRES_MIGRATE_DSN="${POSTGRES_MIGRATE_DSN:-${POSTGRES_DSN}}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up

cd "$MEMORY_DIR"
bash "$ROOT/infra/scripts/memory-uv-sync.sh"
.venv/bin/pytest -q -m integration
