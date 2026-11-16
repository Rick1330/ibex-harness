#!/usr/bin/env bash
# Clean-environment restore drill: compose/podman data plane + optional kind (4.P.5).
# Measured RPO/RTO vs locked targets — reports honestly on miss / non-PITR.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
REPORT_DIR="${RESTORE_DRILL_REPORT_DIR:-/var/lib/ibex/restore-drill}"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/restore-drill-report.json"
TRANSCRIPT="$REPORT_DIR/transcript.txt"
# Fresh transcript per run (do not append prior smoke runs into evidence).
: >"$TRANSCRIPT"

# O03: an RTO measured on a two-row fixture is not evidence. The fixture is
# generated before the backup and the restored row count is recorded in the
# report, so a one-second RTO can never be presented as a real restore time.
DRILL_STARTED_UNIX="$(date +%s)"
DRILL_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FIXTURE_ROWS="${IBEX_DRILL_FIXTURE_ROWS:-50000}"
FIXTURE_ORGS=2
DRILL_MIN_FIXTURE_ROWS="${IBEX_DRILL_MIN_FIXTURE_ROWS:-1000}"
case "$FIXTURE_ROWS" in
  '' | *[!0-9]*) echo "[drill] ERROR: IBEX_DRILL_FIXTURE_ROWS must be a non-negative integer (got '$FIXTURE_ROWS')" >&2; exit 2 ;;
  *) : ;;
esac
case "$DRILL_MIN_FIXTURE_ROWS" in
  '' | *[!0-9]*) echo "[drill] ERROR: IBEX_DRILL_MIN_FIXTURE_ROWS must be a non-negative integer (got '$DRILL_MIN_FIXTURE_ROWS')" >&2; exit 2 ;;
  *) : ;;
esac
exec > >(tee -a "$TRANSCRIPT") 2>&1

echo "=== IBEX 4.P.5 restore drill ==="
echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "root=$ROOT"

# Mechanism selection. `auto` is the historical behaviour: pgBackRest when the
# host runtime and repository are present, pg_dump otherwise. `pgbackrest`
# removes that fallback, because a silent switch to pg_dump is exactly how a
# dump run became a committed report that could never show a PITR mechanism.
# With it set, a missing runtime or repository fails the drill and writes an
# `unavailable` report naming what blocked it. `pg_dump` forces the fallback for
# environments that only want the RTO/isolation half of the drill.
DRILL_MECHANISM="${IBEX_DRILL_MECHANISM:-auto}"
DRILL_TARGET="${IBEX_DRILL_TARGET:-}"
while (( $# > 0 )); do
  case "$1" in
    --mechanism=*) DRILL_MECHANISM="${1#*=}" ;;
    --target=*) DRILL_TARGET="${1#*=}" ;;
    *) echo "[drill] ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$DRILL_MECHANISM" in
  auto | pgbackrest | pg_dump) : ;;
  *) echo "[drill] ERROR: mechanism must be auto, pgbackrest or pg_dump (got '$DRILL_MECHANISM')" >&2; exit 2 ;;
esac
if [[ -n "$DRILL_TARGET" ]] && ! [[ "$DRILL_TARGET" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[T\ ][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}(:?[0-9]{2})?)?$ ]]; then
  echo "[drill] ERROR: --target must be an ISO8601 timestamp (got '$DRILL_TARGET')" >&2
  exit 2
fi
echo "[drill] mechanism=$DRILL_MECHANISM target=${DRILL_TARGET:-<none>}"

if [[ "${ALLOW_NO_DB:-0}" == "1" ]]; then
  cat <<'BANNER'
************************************************************************
*** NOT_EVIDENCE: ALLOW_NO_DB=1 — local/CI smoke only.               ***
*** Do NOT attach this report to Gate G5 / F4-011 / F4-032 PRs.      ***
************************************************************************
BANNER
fi
if [[ "${SKIP_COMPOSE:-0}" == "1" ]]; then
  echo "[drill] NOTE: SKIP_COMPOSE=1 — script did not start compose; POSTGRES_DSN/CONTAINER must already point at a dedicated data plane."
  # Fail closed unless a target is explicit (do not fall through to the default DSN
  # and mutate an unrelated Postgres). Smoke mode (ALLOW_NO_DB=1) may omit both.
  if [[ "${ALLOW_NO_DB:-0}" != "1" && -z "${POSTGRES_CONTAINER:-}" && -z "${POSTGRES_DSN:-}" ]]; then
    echo "[drill] ERROR: SKIP_COMPOSE=1 requires POSTGRES_CONTAINER or POSTGRES_DSN" >&2
    exit 1
  fi
fi

# Locked targets (decision 4) — do not invent different numbers.
PG_RPO_SEC=$((5 * 60))
# The target is operator-configurable (O03): the report computes rto_pass
# against this value, not against a constant a fast run always clears.
# 1800 is the 30-minute target written as a literal rather than `$((30 * 60))`:
# Sonar's shell analyzer reads the `*` in the arithmetic expansion as a glob
# (shell:S6573) and cannot be silenced with NOSONAR on this construct.
PG_RTO_SEC="${IBEX_RTO_TARGET_SEC:-1800}"
case "$PG_RTO_SEC" in
  '' | *[!0-9]* | 0) echo "[drill] ERROR: IBEX_RTO_TARGET_SEC must be a positive integer (got '$PG_RTO_SEC')" >&2; exit 2 ;;
  *) : ;;
esac
CH_RPO_SEC=$((24 * 3600))
CH_RTO_SEC=$((60 * 60))
OBJ_RPO_SEC=$((24 * 3600))
OBJ_RTO_SEC=$((60 * 60))

# environment_class names where the run happened. An operator reading a
# committed report needs to know whether it came from a laptop profile, a CI
# runner or a host, because a local result is not a hosted result.
drill_environment_class() {
  if [[ -n "${IBEX_DRILL_ENVIRONMENT_CLASS:-}" ]]; then
    printf '%s\n' "$IBEX_DRILL_ENVIRONMENT_CLASS"
    return 0
  fi
  local engine="host"
  if [[ -n "${PG_RUNTIME:-}" ]]; then
    engine="$PG_RUNTIME"
  elif command -v docker >/dev/null 2>&1; then
    engine=docker
  elif command -v podman >/dev/null 2>&1; then
    engine=podman
  fi
  if [[ "${SKIP_COMPOSE:-0}" == "1" ]]; then
    printf 'local-%s-external\n' "$engine"
  else
    printf 'local-%s-compose\n' "$engine"
  fi
}

# pgbackrest_blocked_reason prints why the pgBackRest path cannot run here, or
# returns 1 when it can. The checks mirror the branch that actually runs the
# backup, so a reason is never printed for a path that would have worked.
pgbackrest_blocked_reason() {
  if [[ -n "$PG_RUNTIME" ]]; then
    printf 'postgres is bound to container %s via %s; pgBackRest targets the compose volume, not a container exec target\n' \
      "$PG_CONTAINER" "$PG_RUNTIME"
    return 0
  fi
  if ! command -v pgbackrest >/dev/null 2>&1; then
    printf 'the pgbackrest binary is not installed on this host\n'
    return 0
  fi
  if [[ ! -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
    printf 'the pgBackRest repository config is missing (infra/backup/pgbackrest/pgbackrest.conf; run make v1-secrets)\n'
    return 0
  fi
  return 1
}

# emit_unavailable_report writes the honest artefact for a run that could not
# use the requested mechanism. A missing report is not a pass; a report that
# says "unavailable, blocked by X" is. The writer refuses an unavailable report
# without blocked_by, and refuses rpo_pass on one.
emit_unavailable_report() {
  local blocked_by="$1"
  echo "[drill] writing unavailable report: $REPORT"
  REPORT="$REPORT" \
    TRANSCRIPT="$TRANSCRIPT" \
    ALLOW_NO_DB="${ALLOW_NO_DB:-0}" \
    DRILL_KIND=restore-drill \
    DRILL_STARTED_AT="$DRILL_STARTED_AT" \
    ENVIRONMENT_CLASS="$(drill_environment_class)" \
    PG_MECHANISM=unavailable \
    PG_BACKUP_OK=false \
    PG_RESTORE_OK=false \
    PG_RPO_SEC="$PG_RPO_SEC" \
    PG_RTO_SEC="$PG_RTO_SEC" \
    ISO_OK=false \
    KIND_OK=false \
    KYVERNO_OK=false \
    WAL_ARCHIVE_OK=false \
    TARGET_TIMESTAMP="$DRILL_TARGET" \
    BLOCKED_BY="$blocked_by" \
    python3 "$ROOT/infra/scripts/platform/restore_drill_report.py"
}

COMPOSE_FILE="${COMPOSE_FILE:-infra/compose/dev/docker-compose.yml}"
PG_CONTAINER="${POSTGRES_CONTAINER:-}"
PG_RUNTIME=""
if [[ -n "$PG_CONTAINER" ]]; then
  if command -v podman >/dev/null 2>&1 && podman inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    PG_RUNTIME=podman
  elif command -v docker >/dev/null 2>&1 && docker inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    PG_RUNTIME=docker
  else
    echo "[drill] ERROR: POSTGRES_CONTAINER=$PG_CONTAINER not found via podman/docker" >&2
    exit 1
  fi
  echo "[drill] using container runtime=$PG_RUNTIME name=$PG_CONTAINER"
fi

# --mechanism=pgbackrest is a claim that this run proves the PITR path. If the
# path cannot run, the drill fails here — before seeding a fixture or starting a
# stack — and says why. It never degrades into pg_dump.
if [[ "$DRILL_MECHANISM" == "pgbackrest" ]]; then
  if blocked="$(pgbackrest_blocked_reason)"; then
    echo "[drill] ERROR: --mechanism=pgbackrest was requested but pgBackRest cannot run here: $blocked" >&2
    echo "[drill] refusing to fall back to pg_dump: a pg_dump run is not PITR and must not be reported as one" >&2
    emit_unavailable_report "$blocked"
    exit 1
  fi
  echo "[drill] pgBackRest path is mandatory for this run"
fi

if [[ "${SKIP_COMPOSE:-0}" != "1" && -z "$PG_CONTAINER" ]]; then
  echo "[drill] bringing up compose data plane"
  # Do not swallow startup failure — proceeding would risk mutating an unrelated
  # Postgres reached via default/supplied POSTGRES_DSN.
  if ! docker compose -f "$COMPOSE_FILE" up -d postgres redis clickhouse minio 2>/dev/null \
    && ! docker compose -f "$COMPOSE_FILE" up -d; then
    echo "[drill] ERROR: compose data-plane startup failed" >&2
    exit 1
  fi
  sleep 5
fi

PGURL="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
# Require a non-superuser RLS DSN for isolation proof (do not fall back to PGURL).
PG_RLS_URL="${POSTGRES_RLS_DSN:-}"
PG_USER="${POSTGRES_USER:-ibex}"
PG_DB="${POSTGRES_DB:-ibex}"
PG_RLS_USER="${POSTGRES_RLS_USER:-ibex_rls}"
PG_RLS_PASSWORD="${POSTGRES_RLS_PASSWORD:-ibex_rls}"

psql_cmd() {
  if [[ -n "$PG_RUNTIME" ]]; then
    "$PG_RUNTIME" exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" "$@"
  elif command -v psql >/dev/null 2>&1; then
    psql "$PGURL" "$@"
  elif docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q Up; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
      psql -U "${POSTGRES_USER:-ibex}" -d "${POSTGRES_DB:-ibex}" "$@"
  else
    return 127
  fi
}

psql_rls() {
  if [[ -n "$PG_RUNTIME" ]]; then
    # Use resolved PG_RLS_USER (defaults to ibex_rls), not raw POSTGRES_RLS_USER.
    if [[ -z "$PG_RLS_URL" && -z "$PG_RLS_USER" ]]; then
      return 127
    fi
    "$PG_RUNTIME" exec -e "PGPASSWORD=$PG_RLS_PASSWORD" -i "$PG_CONTAINER" \
      psql -U "$PG_RLS_USER" -d "$PG_DB" "$@"
  else
    if [[ -z "$PG_RLS_URL" ]]; then
      return 127
    fi
    if command -v psql >/dev/null 2>&1; then
      psql "$PG_RLS_URL" "$@"
    else
      return 127
    fi
  fi
}

pg_dump_cmd() {
  local out="$1"
  if [[ -n "$PG_RUNTIME" ]]; then
    "$PG_RUNTIME" exec -i "$PG_CONTAINER" \
      pg_dump -U "$PG_USER" -d "$PG_DB" -Fc >"$out"
  elif command -v pg_dump >/dev/null 2>&1; then
    pg_dump "$PGURL" -Fc -f "$out"
  elif docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q Up; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
      pg_dump -U "${POSTGRES_USER:-ibex}" -d "${POSTGRES_DB:-ibex}" -Fc >"$out"
  else
    return 127
  fi
}

pg_restore_cmd() {
  local dump="$1"
  if [[ -n "$PG_RUNTIME" ]]; then
    "$PG_RUNTIME" exec -i "$PG_CONTAINER" \
      pg_restore --clean --if-exists -U "$PG_USER" -d "$PG_DB" <"$dump"
  elif command -v pg_restore >/dev/null 2>&1; then
    pg_restore --clean --if-exists -d "$PGURL" "$dump"
  elif docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q Up; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
      pg_restore --clean --if-exists -U "${POSTGRES_USER:-ibex}" -d "${POSTGRES_DB:-ibex}" \
      <"$dump"
  else
    return 127
  fi
}

# Floor sub-second successful timings to 1s so measured fields are non-zero.
floor_sec() {
  local v="$1"
  if [[ -z "$v" ]]; then
    echo ""
    return
  fi
  if [[ "$v" -le 0 ]]; then
    echo 1
  else
    echo "$v"
  fi
}

# Per-run fixture UUIDs — never reuse fixed tenant IDs that could collide with real data.
ORG_A="$(python3 -c 'import uuid; print(uuid.uuid4())')"
ORG_B="$(python3 -c 'import uuid; print(uuid.uuid4())')"
ORG_A_SLUG="drill-a-${ORG_A%%-*}"
ORG_B_SLUG="drill-b-${ORG_B%%-*}"
echo "[drill] seeding org markers org_a=$ORG_A org_b=$ORG_B"
if ! psql_cmd -v ON_ERROR_STOP=1 <<SQL
INSERT INTO ibex_core.organizations (id, name, slug, status)
VALUES
  ('$ORG_A'::uuid, 'Drill Org A', '$ORG_A_SLUG', 'active'),
  ('$ORG_B'::uuid, 'Drill Org B', '$ORG_B_SLUG', 'active')
ON CONFLICT (id) DO NOTHING;
SQL
then
  echo "[drill] ERROR: seed insert failed — is the schema migrated?" >&2
  if [[ "${ALLOW_NO_DB:-0}" != "1" ]]; then
    exit 1
  fi
fi

# Fixture agents: memories carry a composite FK to (agent_id, org_id), so a
# fixture without agents cannot be inserted. Both tables are FORCE-RLS, so the
# seed runs with app.is_service_account for this controlled, per-run fixture.
AGENT_A="$(python3 -c 'import uuid; print(uuid.uuid4())')"
AGENT_B="$(python3 -c 'import uuid; print(uuid.uuid4())')"
FIXTURE_ROWS_ACTUAL=""
if [[ "${ALLOW_NO_DB:-0}" != "1" ]]; then
  echo "[drill] seeding fixture agents"
  if ! psql_cmd -v ON_ERROR_STOP=1 <<SQL
BEGIN;
SET LOCAL app.is_service_account = 'true';
INSERT INTO ibex_core.agents (id, org_id, name, slug)
VALUES
  ('$AGENT_A'::uuid, '$ORG_A'::uuid, 'Drill Agent A', 'drill-agent'),
  ('$AGENT_B'::uuid, '$ORG_B'::uuid, 'Drill Agent B', 'drill-agent')
ON CONFLICT (org_id, slug) DO NOTHING;
COMMIT;
SQL
  then
    echo "[drill] ERROR: fixture agent seed failed" >&2
    exit 1
  fi
  echo "[drill] seeding fixture rows=$FIXTURE_ROWS across orgs=$FIXTURE_ORGS"
  if ! psql_cmd -v ON_ERROR_STOP=1 <<SQL
BEGIN;
SET LOCAL app.is_service_account = 'true';
INSERT INTO ibex_core.memories (org_id, agent_id, content, content_hash, content_tokens, status)
SELECT
  CASE WHEN g % 2 = 0 THEN '$ORG_A'::uuid ELSE '$ORG_B'::uuid END,
  CASE WHEN g % 2 = 0 THEN '$AGENT_A'::uuid ELSE '$AGENT_B'::uuid END,
  'drill fixture row ' || g,
  md5('drill-fixture-' || g),
  4,
  'active'
FROM generate_series(1, $FIXTURE_ROWS) AS g;
COMMIT;
SQL
  then
    echo "[drill] ERROR: fixture insert failed" >&2
    exit 1
  fi
  FIXTURE_ROWS_ACTUAL="$(psql_cmd -Atc "SET app.is_service_account = 'true'; SELECT COUNT(*)::text FROM ibex_core.memories WHERE org_id IN ('$ORG_A'::uuid, '$ORG_B'::uuid)" 2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true)"
  echo "[drill] fixture rows verified=${FIXTURE_ROWS_ACTUAL:-unknown}"
fi

PG_BACKUP_OK=false
PG_RESTORE_OK=false
PG_BACKUP_SEC=""
PG_RTO_MEASURED=""
PG_RPO_MEASURED=""

# WAL archive freshness is the only honest source for Postgres RPO: it is the
# age of the newest recoverable segment. It is measured *before* the backup,
# because a backup forces a WAL switch and a measurement taken afterwards would
# always look fresh — a number that flatters itself is not evidence.
WAL_ARCHIVE_OK=false
WAL_ARCHIVE_AGE_SEC=""
measure_wal_archive() {
  local row archived last_epoch now
  row="$(psql_cmd -Atc "SELECT archived_count || '|' || COALESCE(EXTRACT(EPOCH FROM last_archived_time)::bigint, -1) FROM pg_stat_archiver" 2>/dev/null | tr -d '\r' | tail -n1 || true)"
  if [[ -z "$row" || "$row" != *"|"* ]]; then
    echo "[drill] WAL archive freshness unreadable (pg_stat_archiver)"
    return 0
  fi
  archived="${row%%|*}"
  last_epoch="${row##*|}"
  case "$archived" in '' | *[!0-9]*) return 0 ;; esac
  case "$last_epoch" in '' | *[!0-9]*) return 0 ;; esac
  if (( archived == 0 || last_epoch <= 0 )); then
    echo "[drill] WAL archiving has archived no segment (archived_count=$archived) — RPO unmeasurable"
    return 0
  fi
  WAL_ARCHIVE_OK=true
  now="$(date +%s)"
  WAL_ARCHIVE_AGE_SEC=$(( now - last_epoch ))
  if (( WAL_ARCHIVE_AGE_SEC < 0 )); then
    WAL_ARCHIVE_AGE_SEC=0
  fi
  echo "[drill] wal_archive_ok=true newest_archived_age_sec=$WAL_ARCHIVE_AGE_SEC"
}
measure_wal_archive

PG_BACKUP_START=$(date +%s)
echo "[drill] postgres backup start"
PG_USED_PGBACKREST=false
# pgBackRest scripts target compose Postgres volumes — unsupported when the drill
# is bound to POSTGRES_CONTAINER (podman/docker exec). Use pg_dump for that path.
if [[ "$DRILL_MECHANISM" != "pg_dump" ]] \
  && [[ -z "$PG_RUNTIME" ]] \
  && command -v pgbackrest >/dev/null 2>&1 \
  && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  if bash infra/scripts/platform/pgbackrest-backup.sh full; then
    PG_BACKUP_OK=true
    PG_USED_PGBACKREST=true
  else
    echo "[drill] WARN pgbackrest backup failed"
  fi
else
  if [[ "$DRILL_MECHANISM" == "pg_dump" ]]; then
    echo "[drill] mechanism=pg_dump forces the fallback (this run cannot claim PITR)"
  elif [[ -n "$PG_RUNTIME" ]]; then
    echo "[drill] NOTE: skipping pgBackRest — POSTGRES_CONTAINER=$PG_CONTAINER is not the compose volume target"
  fi
  echo "[drill] using pg_dump fallback for local evidence"
  mkdir -p "$REPORT_DIR/pg"
  if pg_dump_cmd "$REPORT_DIR/pg/ibex.dump"; then
    PG_BACKUP_OK=true
  else
    echo "[drill] WARN pg_dump failed"
  fi
fi
# The mandatory mechanism was available but produced no backup (a repository
# outage, an unarmed stanza). That is an unavailable PITR path, not a licence to
# continue: inducing data loss with no usable backup would destroy the fixture.
if [[ "$DRILL_MECHANISM" == "pgbackrest" && "$PG_BACKUP_OK" != "true" ]]; then
  echo "[drill] ERROR: pgBackRest backup failed; refusing to continue without a recoverable backup" >&2
  emit_unavailable_report "pgBackRest backup failed (repository unreachable or stanza not armed); see the drill transcript"
  exit 1
fi
PG_BACKUP_END=$(date +%s)
if [[ "$PG_BACKUP_OK" == "true" ]]; then
  PG_BACKUP_SEC="$(floor_sec $((PG_BACKUP_END - PG_BACKUP_START)))"
fi

echo "[drill] inducing data loss (delete org B marker)"
if [[ "${ALLOW_NO_DB:-0}" == "1" ]]; then
  echo "[drill] SKIP destructive delete (ALLOW_NO_DB=1 smoke — NOT_EVIDENCE)"
else
  # The fixture children are ON DELETE RESTRICT, so the org marker cannot be
  # removed while they exist. The backup was taken before this block, so the
  # restore still has to bring every fixture row back.
  if ! psql_cmd -v ON_ERROR_STOP=1 <<SQL
BEGIN;
SET LOCAL app.is_service_account = 'true';
DELETE FROM ibex_core.memories WHERE org_id='$ORG_B'::uuid;
DELETE FROM ibex_core.agents WHERE org_id='$ORG_B'::uuid;
DELETE FROM ibex_core.organizations WHERE id='$ORG_B'::uuid;
COMMIT;
SQL
  then
    echo "[drill] ERROR: failed to induce data loss" >&2
    exit 1
  fi
  # Confirm deletion before restore (superuser / bypass path).
  GONE="$(psql_cmd -Atc "SELECT COUNT(*) FROM ibex_core.organizations WHERE id='$ORG_B'::uuid" 2>/dev/null || true)"
  echo "[drill] org_b rows after delete=$GONE"
  if [[ "$GONE" != "0" ]]; then
    echo "[drill] ERROR: data-loss marker was not deleted" >&2
    exit 1
  fi
fi

PG_RESTORE_START=$(date +%s)
PG_RESTORE_USED_PGBACKREST=false
if [[ -n "$DRILL_TARGET" ]]; then
  # The restore script validates the ISO8601 form and normalises it for
  # pgBackRest's --target parser; the drill does not reshape it.
  PGBACKREST_RESTORE_TARGET="$DRILL_TARGET"
  export PGBACKREST_RESTORE_TARGET
fi
# The pgBackRest restore writes through Compose (a named volume) only when no
# host data directory is supplied. With PGBACKREST_PGDATA set it restores through
# pg_ctl into that host directory, and the Compose PG_VERSION probe below would
# then inspect a different cluster and fail a successful host restore.
PG_RESTORE_USED_COMPOSE=false
if [[ -z "${PGBACKREST_PGDATA:-}" ]]; then
  PG_RESTORE_USED_COMPOSE=true
fi
# The restore follows the mechanism the backup used. A pg_dump backup is
# restored with pg_restore even on a host where pgBackRest is installed,
# otherwise the run would report pg_dump_fallback while restoring a pgBackRest
# set — the drift this drill exists to remove.
if [[ "$DRILL_MECHANISM" != "pg_dump" ]] \
  && [[ -z "$PG_RUNTIME" ]] \
  && command -v pgbackrest >/dev/null 2>&1 \
  && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  if bash infra/scripts/platform/pgbackrest-restore.sh; then
    PG_RESTORE_OK=true
    PG_RESTORE_USED_PGBACKREST=true
  else
    echo "[drill] WARN pgbackrest restore failed"
  fi
elif [[ "$DRILL_MECHANISM" != "pg_dump" ]] \
  && [[ -n "$PG_RUNTIME" ]] \
  && command -v pgbackrest >/dev/null 2>&1 \
  && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  echo "[drill] ERROR: pgBackRest restore targets compose volumes, not POSTGRES_CONTAINER=$PG_CONTAINER" >&2
  echo "[drill] using pg_dump restore for the container data plane instead"
  if [[ -f "$REPORT_DIR/pg/ibex.dump" ]] && pg_restore_cmd "$REPORT_DIR/pg/ibex.dump"; then
    PG_RESTORE_OK=true
  else
    echo "[drill] WARN pg_restore failed — not claiming restore success"
  fi
elif [[ -f "$REPORT_DIR/pg/ibex.dump" ]]; then
  echo "[drill] pg_restore from dump (no re-seed shortcut)"
  if pg_restore_cmd "$REPORT_DIR/pg/ibex.dump"; then
    PG_RESTORE_OK=true
  else
    echo "[drill] WARN pg_restore failed — not claiming restore success"
  fi
fi

# pgBackRest leaves Postgres stopped — restart before post-restore checks.
# Only for compose/pg_ctl paths; POSTGRES_CONTAINER was never stopped by pgBackRest.
if [[ "$PG_RESTORE_USED_PGBACKREST" == "true" ]]; then
  if [[ -n "$PG_RUNTIME" ]]; then
    echo "[drill] ERROR: unexpected pgBackRest path with POSTGRES_CONTAINER set" >&2
    exit 1
  fi
  echo "[drill] restarting Postgres after pgBackRest restore"
  if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
    docker compose -f "$COMPOSE_FILE" start postgres 2>/dev/null \
      || docker compose -f "$COMPOSE_FILE" up -d postgres 2>/dev/null \
      || true
  fi
  if command -v pg_ctl >/dev/null 2>&1 && [[ -d "${PGBACKREST_PGDATA:-}" ]]; then
    pg_ctl -D "$PGBACKREST_PGDATA" start 2>/dev/null || true
  fi
  ready=false
  for _ in $(seq 1 60); do
    if psql_cmd -v ON_ERROR_STOP=1 -Atc "SELECT 1" >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  if [[ "$ready" != "true" ]]; then
    echo "[drill] WARN Postgres did not accept connections after restore restart"
  fi
  # A restore that returned 0 is not evidence until the data directory exists
  # and the server has left recovery. Check PG_VERSION first: a server started
  # over an empty PGDATA runs initdb, so a liveness check alone would report a
  # fresh cluster as a successful restore.
  if [[ "$PG_RESTORE_USED_COMPOSE" == "true" ]] \
    && command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
    if ! docker compose -f "$COMPOSE_FILE" exec -T postgres \
      sh -c 'test -f "${PGDATA:-/var/lib/postgresql/data}/PG_VERSION"' 2>/dev/null; then
      echo "[drill] ERROR: restored data directory has no PG_VERSION — the restore did not produce a cluster" >&2
      PG_RESTORE_OK=false
    fi
  fi
  RECOVERY_STATE="$(psql_cmd -Atc "SELECT pg_is_in_recovery()" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ "$RECOVERY_STATE" != "f" ]]; then
    echo "[drill] ERROR: pg_is_in_recovery()=${RECOVERY_STATE:-no answer} after restore — not claiming restore success" >&2
    PG_RESTORE_OK=false
  fi
fi

PG_RESTORE_END=$(date +%s)

# A requested recovery target is only met when the restored cluster reports a
# last replayed transaction at or before it. Reading the timestamp is the
# evidence; the boolean alone would be an assertion.
RECOVERY_TARGET_REACHED=""
RECOVERY_REPLAY_TIMESTAMP=""
if [[ -n "$DRILL_TARGET" && "$PG_RESTORE_OK" == "true" ]]; then
  replay_epoch="$(psql_cmd -Atc "SELECT COALESCE(EXTRACT(EPOCH FROM pg_last_xact_replay_timestamp())::bigint, -1)" 2>/dev/null | tr -d '[:space:]' | tail -n1 || true)"
  target_epoch="$(date -u -d "$DRILL_TARGET" +%s 2>/dev/null || true)"
  case "$replay_epoch" in '' | *[!0-9-]*) replay_epoch="" ;; esac
  case "$target_epoch" in '' | *[!0-9]*) target_epoch="" ;; esac
  if [[ -n "$replay_epoch" && -n "$target_epoch" ]] && (( replay_epoch >= 0 )); then
    RECOVERY_REPLAY_TIMESTAMP="$(date -u -d "@$replay_epoch" +%Y-%m-%dT%H:%M:%SZ)"
    if (( replay_epoch <= target_epoch )); then
      RECOVERY_TARGET_REACHED=true
      echo "[drill] recovery target reached: replay=${RECOVERY_REPLAY_TIMESTAMP} target=$DRILL_TARGET"
    else
      RECOVERY_TARGET_REACHED=false
      PG_RESTORE_OK=false
      echo "[drill] ERROR: recovery replayed past the target (replay=${RECOVERY_REPLAY_TIMESTAMP} target=$DRILL_TARGET)" >&2
    fi
  else
    RECOVERY_TARGET_REACHED=false
    PG_RESTORE_OK=false
    echo "[drill] ERROR: could not read pg_last_xact_replay_timestamp(); target not proven" >&2
  fi
fi

if [[ "$PG_RESTORE_OK" == "true" ]]; then
  PG_RTO_MEASURED="$(floor_sec $((PG_RESTORE_END - PG_RESTORE_START)))"
fi
# RPO is the age of the latest recoverable WAL/recovery point — NOT backup duration.
# pg_dump cannot measure RPO. pgBackRest measures it from the archive freshness
# observed before the backup; when archiving is not proven fresh the field stays
# null and rpo_pass stays false, which is the honest answer.
PG_RPO_MEASURED=""
if [[ -n "$PG_BACKUP_SEC" ]]; then
  echo "[drill] backup_wall_clock_sec=$PG_BACKUP_SEC (not exported as RPO)"
fi
if [[ "$PG_USED_PGBACKREST" == "true" && "$WAL_ARCHIVE_OK" == "true" ]]; then
  PG_RPO_MEASURED="$WAL_ARCHIVE_AGE_SEC"
  echo "[drill] postgres RPO measured from WAL archive age: ${PG_RPO_MEASURED}s"
else
  echo "[drill] postgres RPO left unmeasured — requires pgBackRest WAL archiving (#869)"
fi

# Tenant isolation under RLS: requires POSTGRES_RLS_DSN or container RLS user.
ISO_OK=false
if [[ -z "$PG_RLS_URL" && -z "$PG_RUNTIME" ]]; then
  echo "[drill] POSTGRES_RLS_DSN unset — tenant isolation unproven (do not use superuser PGURL)"
elif [[ -n "$PG_RUNTIME" ]] || [[ -n "$PG_RLS_URL" ]]; then
  # Mark RLS intent for container path even when DSN string unused.
  if [[ -z "$PG_RLS_URL" && -n "$PG_RUNTIME" ]]; then
    PG_RLS_URL="container://${PG_RLS_USER}@${PG_CONTAINER}/${PG_DB}"
  fi
  # Multi-statement -Atc prints SET/COMMIT lines; keep only integer COUNT rows.
  rls_count() {
    local org_guc="$1" target_id="$2"
    psql_rls -v ON_ERROR_STOP=1 -Atc "
BEGIN;
SET LOCAL ROLE ibex_app;
SELECT set_config('app.current_org_id', '$org_guc', true);
SELECT COUNT(*)::text FROM ibex_core.organizations WHERE id='$target_id'::uuid;
COMMIT;
" 2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true
  }
  ISO_A_OWN="$(rls_count "$ORG_A" "$ORG_A")"
  ISO_A_CROSS="$(rls_count "$ORG_A" "$ORG_B")"
  ISO_B_OWN="$(rls_count "$ORG_B" "$ORG_B")"
  ISO_B_CROSS="$(rls_count "$ORG_B" "$ORG_A")"
  RESTORED_B="$(psql_cmd -Atc "SELECT COUNT(*) FROM ibex_core.organizations WHERE id='$ORG_B'::uuid" 2>/dev/null || true)"
  echo "[drill] post-restore org_b rows (superuser)=$RESTORED_B"
  if [[ "$RESTORED_B" == "1" && "$ISO_A_OWN" == "1" && "$ISO_B_OWN" == "1" && "$ISO_A_CROSS" == "0" && "$ISO_B_CROSS" == "0" ]]; then
    ISO_OK=true
  fi
  echo "[drill] tenant isolation A_own=$ISO_A_OWN A_cross=$ISO_A_CROSS B_own=$ISO_B_OWN B_cross=$ISO_B_CROSS ok=$ISO_OK"
fi

# cluster_data_bytes and the table counts are what make a restore report
# legible: "reached the target" over an empty database is not a recovery.
CLUSTER_DATA_BYTES=""
RESTORED_ORGS=""
RESTORED_MEMORIES=""
if [[ "$PG_RESTORE_OK" == "true" && "${ALLOW_NO_DB:-0}" != "1" ]]; then
  CLUSTER_DATA_BYTES="$(psql_cmd -Atc "SELECT pg_database_size(current_database())" 2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true)"
  RESTORED_ORGS="$(psql_cmd -Atc "SELECT COUNT(*)::text FROM ibex_core.organizations" 2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true)"
  RESTORED_MEMORIES="$(psql_cmd -Atc "SET app.is_service_account = 'true'; SELECT COUNT(*)::text FROM ibex_core.memories" 2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true)"
  echo "[drill] restored cluster bytes=${CLUSTER_DATA_BYTES:-unknown} orgs=${RESTORED_ORGS:-unknown} memories=${RESTORED_MEMORIES:-unknown}"
fi

FIXTURE_ROWS_RESTORED=""
if [[ "${ALLOW_NO_DB:-0}" != "1" && -n "$FIXTURE_ROWS_ACTUAL" ]]; then
  FIXTURE_ROWS_RESTORED="$(psql_cmd -Atc "SET app.is_service_account = 'true'; SELECT COUNT(*)::text FROM ibex_core.memories WHERE org_id IN ('$ORG_A'::uuid, '$ORG_B'::uuid)" 2>/dev/null | grep -E '^[0-9]+$' | tail -n1 || true)"
  echo "[drill] post-restore fixture rows=${FIXTURE_ROWS_RESTORED:-unknown}"
fi

CH_RTO_MEASURED=""
CH_RPO_MEASURED=""
OBJ_RTO_MEASURED=""
OBJ_RPO_MEASURED=""
CH_REACHABLE=false
if command -v clickhouse-client >/dev/null 2>&1; then
  CH_START=$(date +%s)
  if clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
    CH_REACHABLE=true
    CH_RTO_MEASURED=$(( $(date +%s) - CH_START ))
  fi
fi

OUTBOX_SEQ="$(psql_cmd -Atc "SELECT COALESCE(MAX(aggregate_seq),0) FROM ibex_core.evidence_outbox" 2>/dev/null || true)"
OUTBOX_PENDING="$(psql_cmd -Atc "SELECT COUNT(*) FROM ibex_core.evidence_outbox WHERE delivery_status='pending'" 2>/dev/null || true)"

KIND_OK=false
KYVERNO_OK=false
if command -v helm >/dev/null 2>&1; then
  echo "[drill] helm lint + template"
  helm lint infra/helm/ibex-harness -f infra/helm/ibex-harness/values-ci-lint.yaml
  helm template ibex infra/helm/ibex-harness -f infra/helm/ibex-harness/values-ci-lint.yaml >"$REPORT_DIR/ibex-render.yaml"
  KIND_OK=true
fi
if [[ "${RUN_KIND:-0}" == "1" ]] && command -v kind >/dev/null 2>&1; then
  KIND_CTX="kind-ibex-4p5-drill"
  # Do not ignore create failure — a failed create + bare kubectl would apply
  # verify-images to whatever the current context is (unsafe).
  if ! kind get clusters 2>/dev/null | grep -qx 'ibex-4p5-drill'; then
    kind create cluster --name ibex-4p5-drill
  fi
  if command -v kubectl >/dev/null 2>&1; then
    echo "[drill] applying Kyverno verifyImages policy on context=$KIND_CTX"
    kubectl --context "$KIND_CTX" apply -f infra/helm/ibex-harness/policies/verify-images.yaml \
      && KYVERNO_OK=true \
      || echo "[drill] WARN Kyverno policy apply failed (install Kyverno first; residual #869)" >&2
  fi
else
  echo "[drill] Kyverno cluster admit deferred to #869 (RUN_KIND!=1 or kind unavailable)"
fi

PG_MECHANISM="unmeasured"
if [[ "$PG_BACKUP_OK" == "true" ]]; then
  if [[ "$PG_USED_PGBACKREST" == "true" ]]; then
    PG_MECHANISM="pgbackrest_wal"
  else
    PG_MECHANISM="pg_dump_fallback"
  fi
fi

export REPORT PG_RPO_SEC PG_RTO_SEC PG_RPO_MEASURED PG_RTO_MEASURED
export DRILL_KIND=restore-drill DRILL_STARTED_AT
ENVIRONMENT_CLASS="$(drill_environment_class)"
export ENVIRONMENT_CLASS
export WAL_ARCHIVE_OK TARGET_TIMESTAMP="$DRILL_TARGET"
export RECOVERY_TARGET_REACHED RECOVERY_REPLAY_TIMESTAMP
export CLUSTER_DATA_BYTES RESTORED_ORGS RESTORED_MEMORIES
export BLOCKED_BY=""
export CH_RPO_SEC CH_RTO_SEC CH_RPO_MEASURED CH_RTO_MEASURED CH_REACHABLE
export OBJ_RPO_SEC OBJ_RTO_SEC OBJ_RPO_MEASURED OBJ_RTO_MEASURED
export OUTBOX_SEQ OUTBOX_PENDING ISO_OK KIND_OK KYVERNO_OK TRANSCRIPT PG_MECHANISM
export PG_BACKUP_OK PG_RESTORE_OK ALLOW_NO_DB
DRILL_DURATION_SEC=$(( $(date +%s) - DRILL_STARTED_UNIX ))
export FIXTURE_ROWS FIXTURE_ORGS FIXTURE_ROWS_ACTUAL FIXTURE_ROWS_RESTORED
export DRILL_MIN_FIXTURE_ROWS DRILL_DURATION_SEC
python3 "$ROOT/infra/scripts/platform/restore_drill_report.py"

echo "report=$REPORT"
echo "ended_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
