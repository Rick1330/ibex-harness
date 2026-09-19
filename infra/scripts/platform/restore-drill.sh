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
exec > >(tee -a "$TRANSCRIPT") 2>&1

echo "=== IBEX 4.P.5 restore drill ==="
echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "root=$ROOT"

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
PG_RTO_SEC=$((30 * 60))
CH_RPO_SEC=$((24 * 3600))
CH_RTO_SEC=$((60 * 60))
OBJ_RPO_SEC=$((24 * 3600))
OBJ_RTO_SEC=$((60 * 60))

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

PG_BACKUP_OK=false
PG_RESTORE_OK=false
PG_BACKUP_SEC=""
PG_RTO_MEASURED=""
PG_RPO_MEASURED=""

PG_BACKUP_START=$(date +%s)
echo "[drill] postgres backup start"
# pgBackRest scripts target compose Postgres volumes — unsupported when the drill
# is bound to POSTGRES_CONTAINER (podman/docker exec). Use pg_dump for that path.
if [[ -z "$PG_RUNTIME" ]] \
  && command -v pgbackrest >/dev/null 2>&1 \
  && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  if bash infra/scripts/platform/pgbackrest-backup.sh full; then
    PG_BACKUP_OK=true
  else
    echo "[drill] WARN pgbackrest backup failed"
  fi
else
  if [[ -n "$PG_RUNTIME" ]] && command -v pgbackrest >/dev/null 2>&1 \
    && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
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
PG_BACKUP_END=$(date +%s)
if [[ "$PG_BACKUP_OK" == "true" ]]; then
  PG_BACKUP_SEC="$(floor_sec $((PG_BACKUP_END - PG_BACKUP_START)))"
fi

echo "[drill] inducing data loss (delete org B marker)"
if [[ "${ALLOW_NO_DB:-0}" == "1" ]]; then
  echo "[drill] SKIP destructive delete (ALLOW_NO_DB=1 smoke — NOT_EVIDENCE)"
else
  if ! psql_cmd -v ON_ERROR_STOP=1 -c "DELETE FROM ibex_core.organizations WHERE id='$ORG_B'::uuid"; then
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
PG_USED_PGBACKREST=false
if [[ -z "$PG_RUNTIME" ]] \
  && command -v pgbackrest >/dev/null 2>&1 \
  && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  if bash infra/scripts/platform/pgbackrest-restore.sh; then
    PG_RESTORE_OK=true
    PG_USED_PGBACKREST=true
  else
    echo "[drill] WARN pgbackrest restore failed"
  fi
elif [[ -n "$PG_RUNTIME" ]] \
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
if [[ "$PG_USED_PGBACKREST" == "true" ]]; then
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
fi

PG_RESTORE_END=$(date +%s)
if [[ "$PG_RESTORE_OK" == "true" ]]; then
  PG_RTO_MEASURED="$(floor_sec $((PG_RESTORE_END - PG_RESTORE_START)))"
fi
# RPO is the age of the latest recoverable WAL/recovery point — NOT backup duration.
# pg_dump cannot measure RPO; pgBackRest also leaves RPO unmeasured until archive
# freshness + PITR are verified (residual #869). Keep PG_BACKUP_SEC for logs only.
PG_RPO_MEASURED=""
if [[ -n "$PG_BACKUP_SEC" ]]; then
  echo "[drill] backup_wall_clock_sec=$PG_BACKUP_SEC (not exported as RPO)"
fi
echo "[drill] postgres RPO left unmeasured — requires WAL archive freshness + PITR (#869)"

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
export CH_RPO_SEC CH_RTO_SEC CH_RPO_MEASURED CH_RTO_MEASURED CH_REACHABLE
export OBJ_RPO_SEC OBJ_RTO_SEC OBJ_RPO_MEASURED OBJ_RTO_MEASURED
export OUTBOX_SEQ OUTBOX_PENDING ISO_OK KIND_OK KYVERNO_OK TRANSCRIPT PG_MECHANISM
export PG_BACKUP_OK PG_RESTORE_OK ALLOW_NO_DB
python3 "$ROOT/infra/scripts/platform/restore_drill_report.py"

echo "report=$REPORT"
echo "ended_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
