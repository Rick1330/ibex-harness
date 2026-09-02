#!/usr/bin/env bash
# Run services/worker integration tests (Redis broker + migrated Postgres for dead-letter).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKER_DIR="$ROOT/services/worker"

if [[ ! -f "$WORKER_DIR/pyproject.toml" ]]; then
  echo "services/worker not present — worker integration tests required in CI" >&2
  exit 1
fi

export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export REDIS_DB_QUEUE="${REDIS_DB_QUEUE:-1}"
export REDIS_DB_RESULTS="${REDIS_DB_RESULTS:-3}"
export IBEX_WORKER_INTEGRATION_TESTS="${IBEX_WORKER_INTEGRATION_TESTS:-1}"

if [[ -z "${POSTGRES_TEST_DSN:-}" ]]; then
  echo "POSTGRES_TEST_DSN required for worker dead-letter integration tests" >&2
  exit 1
fi

export POSTGRES_DSN="${POSTGRES_TEST_DSN}"
export POSTGRES_MIGRATE_DSN="${POSTGRES_MIGRATE_DSN:-${POSTGRES_TEST_DSN}}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up

cd "$WORKER_DIR"
bash "$ROOT/infra/scripts/worker-uv-sync.sh"
.venv/bin/pytest -q -m integration
