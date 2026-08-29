#!/usr/bin/env bash
# Run Phase 3 memory HTTP lifecycle e2e gate (m3.E.2).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MEMORY_DIR="$ROOT/services/memory"

if [[ ! -f "$MEMORY_DIR/pyproject.toml" ]]; then
  echo "services/memory not present — skipping phase 3 memory e2e"
  exit 0
fi

CANONICAL_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-${IBEX_MEMORY_DATABASE_URL:-}}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "POSTGRES_DSN, POSTGRES_TEST_DSN, or IBEX_MEMORY_DATABASE_URL required" >&2
  exit 1
fi
if [[ -z "${REDIS_URL:-}" ]]; then
  echo "REDIS_URL required for phase 3 memory e2e" >&2
  exit 1
fi

export POSTGRES_DSN="${CANONICAL_DSN}"
export POSTGRES_MIGRATE_DSN="${CANONICAL_DSN}"
export POSTGRES_TEST_DSN="${CANONICAL_DSN}"
export IBEX_MEMORY_DATABASE_URL="${CANONICAL_DSN}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up
bash "$ROOT/infra/scripts/db-seed.sh"
bash "$ROOT/infra/scripts/memory-uv-sync.sh"
bash "$ROOT/infra/scripts/embedder-uv-sync.sh"

export IBEX_E2E_PHASE3_MANAGE=1
bash "$ROOT/infra/scripts/verify_phase3_memory_e2e.sh"
