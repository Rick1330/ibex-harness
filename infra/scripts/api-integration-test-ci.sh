#!/usr/bin/env bash
# Run services/api Postgres integration tests (requires migrated Postgres).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="$ROOT/services/api"

if [[ ! -f "$API_DIR/pyproject.toml" ]]; then
  echo "services/api not present — skipping api integration tests"
  exit 0
fi

CANONICAL_DSN="${POSTGRES_DSN:-${POSTGRES_TEST_DSN:-${IBEX_API_DATABASE_URL:-${IBEX_MEMORY_DATABASE_URL:-}}}}"
if [[ -z "${CANONICAL_DSN}" ]]; then
  echo "POSTGRES_DSN, POSTGRES_TEST_DSN, IBEX_API_DATABASE_URL, or IBEX_MEMORY_DATABASE_URL required" >&2
  exit 1
fi

export POSTGRES_DSN="${CANONICAL_DSN}"
export POSTGRES_MIGRATE_DSN="${CANONICAL_DSN}"
export POSTGRES_TEST_DSN="${CANONICAL_DSN}"
# Integration fixtures accept either API or memory DSN env names.
export IBEX_API_DATABASE_URL="${CANONICAL_DSN}"
export IBEX_MEMORY_DATABASE_URL="${CANONICAL_DSN}"

cd "$ROOT"
bash "$ROOT/infra/scripts/db-migrate.sh" up

cd "$API_DIR"
bash "$ROOT/infra/scripts/api-uv-sync.sh"
.venv/bin/pytest -q -m integration
