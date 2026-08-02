#!/usr/bin/env bash
# Repair orphaned token FK columns after failed migration 000008 or 000012.
# Clears missing-ID orphans and same-ID / wrong-org binds, validates an
# exclusive FK set, then force-cleans schema_migrations only to a version that
# matches the constraints actually present (never force 12 without composites).
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

force_migrate_version() {
  local ver="$1"
  echo "Marking migration version ${ver} clean (force; does not run SQL)..."
  cd "$ROOT_DIR"
  export POSTGRES_MIGRATE_DSN="${POSTGRES_MIGRATE_DSN:-${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}}"
  go run ./infra/migrations/postgres/cmd/migrate -command force -version "$ver"
}

echo "Clearing orphaned and cross-org token foreign keys..."
run_psql <<'SQL'
UPDATE ibex_core.tokens t
SET revoked_by = NULL
WHERE revoked_by IS NOT NULL
  AND revoked_by NOT IN (SELECT id FROM ibex_core.users);

UPDATE ibex_core.tokens t
SET user_id = NULL
FROM ibex_core.users u
WHERE t.user_id = u.id
  AND t.org_id <> u.org_id;

UPDATE ibex_core.tokens t
SET user_id = NULL
WHERE user_id IS NOT NULL
  AND user_id NOT IN (SELECT id FROM ibex_core.users);

UPDATE ibex_core.tokens t
SET agent_id = NULL
FROM ibex_core.agents a
WHERE t.agent_id = a.id
  AND t.org_id <> a.org_id;

UPDATE ibex_core.tokens t
SET agent_id = NULL
WHERE agent_id IS NOT NULL
  AND agent_id NOT IN (SELECT id FROM ibex_core.agents);
SQL

echo "Detecting token FK constraint set..."
# Prints: composite | legacy | mixed | missing
SCHEMA_KIND="$(run_psql -Atc "
SELECT CASE
  WHEN EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_user_org_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_agent_org_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_user_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_agent_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_revoked_by_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'users_id_org_unique'
        AND conrelid = 'ibex_core.users'::regclass
    )
  THEN 'composite'
  WHEN EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_user_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_agent_id_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_user_org_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_agent_org_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
    AND EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = 'tokens_revoked_by_fk' AND conrelid = 'ibex_core.tokens'::regclass
    )
  THEN 'legacy'
  WHEN EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conrelid = 'ibex_core.tokens'::regclass
        AND conname IN (
          'tokens_user_org_fk', 'tokens_agent_org_fk',
          'tokens_user_id_fk', 'tokens_agent_id_fk'
        )
    )
  THEN 'mixed'
  ELSE 'missing'
END;
" | tr -d '\r')"

case "$SCHEMA_KIND" in
  composite)
    echo "Validating composite token subject FKs (000012)..."
    run_psql <<'SQL'
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_org_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_org_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_revoked_by_fk;
SQL
    ;;
  legacy)
    echo "Validating single-column token subject FKs (000008)..."
    run_psql <<'SQL'
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_id_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_id_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_revoked_by_fk;
SQL
    ;;
  mixed)
    echo "error: mixed/partial token subject FKs; refuse repair (re-run 000012 from version 11)" >&2
    exit 1
    ;;
  *)
    echo "error: missing expected token FK constraints; refusing repair" >&2
    exit 1
    ;;
esac

DIRTY_VER="$(run_psql -Atc "SELECT CASE WHEN dirty THEN version::text ELSE '' END FROM schema_migrations LIMIT 1" | tr -d '\r')"
if [[ -z "$DIRTY_VER" ]]; then
  echo "schema_migrations clean; no force needed"
  echo "db-repair-token-fks: ok (run make db-migrate to confirm)"
  exit 0
fi

echo "Dirty schema_migrations at version ${DIRTY_VER} (schema_kind=${SCHEMA_KIND})"
case "$SCHEMA_KIND:$DIRTY_VER" in
  composite:12)
    force_migrate_version 12
    ;;
  legacy:8)
    force_migrate_version 8
    ;;
  legacy:12)
    # 000012 rolled back DDL but left dirty@12; force to 11 so migrate re-applies composites.
    echo "000012 incomplete (legacy FKs only at dirty 12); forcing version 11 for re-apply"
    force_migrate_version 11
    ;;
  *)
    echo "error: dirty version ${DIRTY_VER} incompatible with schema_kind=${SCHEMA_KIND}" >&2
    echo "hint: for rolled-back 000012, force to 11 manually and run make db-migrate" >&2
    exit 1
    ;;
esac

echo "db-repair-token-fks: ok (run make db-migrate to confirm)"
