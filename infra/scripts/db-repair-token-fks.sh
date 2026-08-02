#!/usr/bin/env bash
# Repair orphaned token FK columns after failed migration 000008 or 000012.
# Clears missing-ID orphans and same-ID / wrong-org binds, then validates
# whichever token subject FK constraints are present.
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

echo "Clearing orphaned and cross-org token foreign keys..."
run_psql <<'SQL'
UPDATE ibex_core.tokens t
SET revoked_by = NULL
WHERE revoked_by IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ibex_core.users u WHERE u.id = t.revoked_by);

UPDATE ibex_core.tokens t
SET user_id = NULL
WHERE user_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM ibex_core.users u
      WHERE u.id = t.user_id AND u.org_id = t.org_id
  );

UPDATE ibex_core.tokens t
SET agent_id = NULL
WHERE agent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM ibex_core.agents a
      WHERE a.id = t.agent_id AND a.org_id = t.org_id
  );
SQL

echo "Validating token FK constraints (if present)..."
run_psql <<'SQL'
DO $$
DECLARE
  has_user_id_fk boolean;
  has_agent_id_fk boolean;
  has_user_org_fk boolean;
  has_agent_org_fk boolean;
  has_revoked_fk boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_user_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_user_id_fk;
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_agent_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_agent_id_fk;
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_user_org_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_user_org_fk;
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_agent_org_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_agent_org_fk;
  SELECT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tokens_revoked_by_fk' AND conrelid = 'ibex_core.tokens'::regclass
  ) INTO has_revoked_fk;

  IF has_user_org_fk AND has_agent_org_fk AND has_revoked_fk THEN
    ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_org_fk;
    ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_org_fk;
    ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_revoked_by_fk;
    RAISE NOTICE 'validated composite token subject FKs (000012)';
  ELSIF has_user_id_fk AND has_agent_id_fk AND has_revoked_fk THEN
    ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_id_fk;
    ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_id_fk;
    ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_revoked_by_fk;
    RAISE NOTICE 'validated single-column token subject FKs (000008)';
  ELSE
    RAISE EXCEPTION 'missing expected token FK constraints; refusing repair';
  END IF;
END $$;
SQL

echo "Checking migration dirty state..."
run_psql <<'SQL'
DO $$
DECLARE
  ver bigint;
  dirty boolean;
BEGIN
  SELECT version, dirty INTO ver, dirty FROM schema_migrations LIMIT 1;
  IF NOT FOUND THEN
    RAISE NOTICE 'no schema_migrations row; skip force';
    RETURN;
  END IF;
  IF NOT dirty THEN
    RAISE NOTICE 'schema_migrations clean at version %', ver;
    RETURN;
  END IF;
  IF ver NOT IN (8, 12) THEN
    RAISE EXCEPTION 'dirty schema_migrations version % not supported by this repair (want 8 or 12)', ver;
  END IF;
END $$;
SQL

# Force clean only when dirty at 8 or 12 (validated above).
DIRTY_VER="$(run_psql -Atc "SELECT CASE WHEN dirty THEN version::text ELSE '' END FROM schema_migrations LIMIT 1" | tr -d '\r')"
if [[ -n "$DIRTY_VER" ]]; then
  echo "Marking migration version ${DIRTY_VER} clean..."
  cd "$ROOT_DIR"
  export POSTGRES_MIGRATE_DSN="${POSTGRES_MIGRATE_DSN:-${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}}"
  go run ./infra/migrations/postgres/cmd/migrate -command force -version "$DIRTY_VER"
fi

echo "db-repair-token-fks: ok (run make db-migrate to confirm)"
