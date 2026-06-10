#!/usr/bin/env bash
# Repair orphaned token FK columns and finish migration 000008 validation.
# Use when db-migrate fails with tokens_*_fk and a dirty schema_migrations version.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV_ENV="$ROOT_DIR/infra/compose/dev/.env.example"

if [[ -f "$DEV_ENV" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$DEV_ENV"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-ibex}"
POSTGRES_DB="${POSTGRES_DB:-ibex}"

run_psql() {
  if command -v psql >/dev/null 2>&1; then
    local dsn="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
    dsn="${dsn//postgresql+asyncpg:/postgres:}"
    dsn="${dsn//postgresql:/postgres:}"
    psql "$dsn" -v ON_ERROR_STOP=1 "$@"
    return
  fi
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ibex-dev-postgres; then
    docker exec ibex-dev-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"
    return
  fi
  echo "need psql on PATH or running ibex-dev-postgres (make compose-dev-up)"
  exit 1
}

echo "Clearing orphaned token foreign keys..."
run_psql <<'SQL'
UPDATE ibex_core.tokens t
SET revoked_by = NULL
WHERE revoked_by IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ibex_core.users u WHERE u.id = t.revoked_by);

UPDATE ibex_core.tokens t
SET user_id = NULL
WHERE user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ibex_core.users u WHERE u.id = t.user_id);

UPDATE ibex_core.tokens t
SET agent_id = NULL
WHERE agent_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ibex_core.agents a WHERE a.id = t.agent_id);
SQL

echo "Validating token FK constraints (if present)..."
run_psql <<'SQL'
DO $$
DECLARE
  has_user_fk boolean;
  has_agent_fk boolean;
  has_revoked_fk boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_user_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_user_fk;
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_agent_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_agent_fk;
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_revoked_by_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_revoked_fk;

  IF NOT (has_user_fk AND has_agent_fk AND has_revoked_fk) THEN
    RAISE EXCEPTION 'missing expected token FK constraints; refusing to force migration version 8 clean';
  END IF;

  ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_id_fk;
  ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_id_fk;
  ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_revoked_by_fk;
END $$;
SQL

echo "Marking migration version 8 clean..."
cd "$ROOT_DIR"
export POSTGRES_MIGRATE_DSN="${POSTGRES_MIGRATE_DSN:-${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}}"
go run ./infra/migrations/postgres/cmd/migrate -command force -version 8

echo "db-repair-token-fks: ok (run make db-migrate to confirm)"
