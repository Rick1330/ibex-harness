#!/usr/bin/env bash
# CI wrapper for Phase 3.5 learning-loop e2e (3.5.F.1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

CANONICAL_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-${IBEX_MEMORY_DATABASE_URL:-}}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "POSTGRES_DSN, POSTGRES_TEST_DSN, or IBEX_MEMORY_DATABASE_URL required" >&2
  exit 1
fi
if [[ -z "${REDIS_URL:-}" ]]; then
  echo "REDIS_URL required for phase 3.5 e2e" >&2
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
bash "$ROOT/infra/scripts/worker-uv-sync.sh"
bash "$ROOT/infra/scripts/context-uv-sync.sh"
bash "$ROOT/infra/scripts/mcp-memory-uv-sync.sh"
bash "$ROOT/infra/scripts/context-proto-gen.sh"

export IBEX_E2E_P35_MANAGE=1
# GHA postgres/redis are on 5432/6379; compose-test defaults overridden by env.
bash "$ROOT/infra/scripts/e2e_phase35.sh"
