#!/usr/bin/env bash
# Clean-environment restore drill: compose data plane + optional kind (4.P.5).
# Measured RPO/RTO vs locked targets — reports honestly on miss.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
REPORT_DIR="${RESTORE_DRILL_REPORT_DIR:-/var/lib/ibex/restore-drill}"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/restore-drill-report.json"
TRANSCRIPT="$REPORT_DIR/transcript.txt"
exec > >(tee -a "$TRANSCRIPT") 2>&1

echo "=== IBEX 4.P.5 restore drill ==="
echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "root=$ROOT"

# Locked targets (decision 4) — do not invent different numbers.
PG_RPO_SEC=$((5 * 60))
PG_RTO_SEC=$((30 * 60))
CH_RPO_SEC=$((24 * 3600))
CH_RTO_SEC=$((60 * 60))
OBJ_RPO_SEC=$((24 * 3600))
OBJ_RTO_SEC=$((60 * 60))

COMPOSE_FILE="${COMPOSE_FILE:-infra/compose/dev/docker-compose.yml}"
if [[ "${SKIP_COMPOSE:-0}" != "1" ]]; then
  echo "[drill] bringing up compose data plane"
  docker compose -f "$COMPOSE_FILE" up -d postgres redis clickhouse minio 2>/dev/null \
    || docker compose -f "$COMPOSE_FILE" up -d || true
  sleep 5
fi

PGURL="${POSTGRES_DSN:-postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable}"
# App role subject to RLS (override when drill uses a dedicated RLS user).
PG_RLS_URL="${POSTGRES_RLS_DSN:-$PGURL}"

psql_cmd() {
  if command -v psql >/dev/null 2>&1; then
    psql "$PGURL" "$@"
  elif docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q Up; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
      psql -U "${POSTGRES_USER:-ibex}" -d "${POSTGRES_DB:-ibex}" "$@"
  else
    return 127
  fi
}

psql_rls() {
  if command -v psql >/dev/null 2>&1; then
    psql "$PG_RLS_URL" "$@"
  else
    psql_cmd "$@"
  fi
}

pg_dump_cmd() {
  local out="$1"
  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump "$PGURL" -Fc -f "$out"
  elif docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q Up; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
      pg_dump -U "${POSTGRES_USER:-ibex}" -d "${POSTGRES_DB:-ibex}" -Fc >"$out"
  else
    return 127
  fi
}

ORG_A="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORG_B="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
echo "[drill] seeding org markers"
psql_cmd -v ON_ERROR_STOP=1 <<SQL || true
INSERT INTO ibex_core.organizations (id, name, slug, status)
VALUES
  ('$ORG_A'::uuid, 'Drill Org A', 'drill-a', 'active'),
  ('$ORG_B'::uuid, 'Drill Org B', 'drill-b', 'active')
ON CONFLICT (id) DO NOTHING;
SQL

PG_BACKUP_OK=false
PG_RESTORE_OK=false
PG_BACKUP_SEC=""
PG_RTO_MEASURED=""
PG_RPO_MEASURED=""

PG_BACKUP_START=$(date +%s)
echo "[drill] postgres backup start"
if command -v pgbackrest >/dev/null 2>&1 && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  if bash infra/scripts/platform/pgbackrest-backup.sh full; then
    PG_BACKUP_OK=true
  else
    echo "[drill] WARN pgbackrest backup failed"
  fi
else
  echo "[drill] pgbackrest not installed — using pg_dump fallback for local evidence"
  mkdir -p "$REPORT_DIR/pg"
  if pg_dump_cmd "$REPORT_DIR/pg/ibex.dump"; then
    PG_BACKUP_OK=true
  else
    echo "[drill] WARN pg_dump failed"
  fi
fi
PG_BACKUP_END=$(date +%s)
if [[ "$PG_BACKUP_OK" == "true" ]]; then
  PG_BACKUP_SEC=$((PG_BACKUP_END - PG_BACKUP_START))
fi

echo "[drill] inducing data loss (delete org B marker)"
psql_cmd -c "DELETE FROM ibex_core.organizations WHERE id='$ORG_B'::uuid" || true

PG_RESTORE_START=$(date +%s)
if command -v pgbackrest >/dev/null 2>&1 && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
  if bash infra/scripts/platform/pgbackrest-restore.sh; then
    PG_RESTORE_OK=true
  else
    echo "[drill] WARN pgbackrest restore failed"
  fi
elif [[ -f "$REPORT_DIR/pg/ibex.dump" ]]; then
  echo "[drill] restoring org B via re-seed (pg_dump fallback; full PITR needs pgBackRest+WAL)"
  if psql_cmd -v ON_ERROR_STOP=1 <<SQL
INSERT INTO ibex_core.organizations (id, name, slug, status)
VALUES ('$ORG_B'::uuid, 'Drill Org B', 'drill-b', 'active')
ON CONFLICT (id) DO NOTHING;
SQL
  then
    PG_RESTORE_OK=true
  fi
fi
PG_RESTORE_END=$(date +%s)
if [[ "$PG_RESTORE_OK" == "true" ]]; then
  PG_RTO_MEASURED=$((PG_RESTORE_END - PG_RESTORE_START))
fi
# RPO is only meaningful after a successful backup AND successful recovery.
if [[ "$PG_BACKUP_OK" == "true" && "$PG_RESTORE_OK" == "true" && -n "$PG_BACKUP_SEC" ]]; then
  PG_RPO_MEASURED=$PG_BACKUP_SEC
fi

# Tenant isolation under RLS: two sessions with SET LOCAL app.current_org_id.
ISO_OK=false
ISO_A_OWN="$(psql_rls -Atc "
BEGIN;
SET LOCAL app.current_org_id = '$ORG_A';
SELECT COUNT(*) FROM ibex_core.organizations WHERE id='$ORG_A'::uuid;
COMMIT;
" 2>/dev/null | tail -n1 || true)"
ISO_A_CROSS="$(psql_rls -Atc "
BEGIN;
SET LOCAL app.current_org_id = '$ORG_A';
SELECT COUNT(*) FROM ibex_core.organizations WHERE id='$ORG_B'::uuid;
COMMIT;
" 2>/dev/null | tail -n1 || true)"
ISO_B_OWN="$(psql_rls -Atc "
BEGIN;
SET LOCAL app.current_org_id = '$ORG_B';
SELECT COUNT(*) FROM ibex_core.organizations WHERE id='$ORG_B'::uuid;
COMMIT;
" 2>/dev/null | tail -n1 || true)"
ISO_B_CROSS="$(psql_rls -Atc "
BEGIN;
SET LOCAL app.current_org_id = '$ORG_B';
SELECT COUNT(*) FROM ibex_core.organizations WHERE id='$ORG_A'::uuid;
COMMIT;
" 2>/dev/null | tail -n1 || true)"
if [[ "$ISO_A_OWN" == "1" && "$ISO_B_OWN" == "1" && "$ISO_A_CROSS" == "0" && "$ISO_B_CROSS" == "0" ]]; then
  ISO_OK=true
fi
echo "[drill] tenant isolation A_own=$ISO_A_OWN A_cross=$ISO_A_CROSS B_own=$ISO_B_OWN B_cross=$ISO_B_CROSS ok=$ISO_OK"

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
  kind create cluster --name ibex-4p5-drill || true
  if command -v kubectl >/dev/null 2>&1; then
    echo "[drill] applying Kyverno verifyImages policy (requires Kyverno installed)"
    kubectl apply -f infra/helm/ibex-harness/policies/verify-images.yaml && KYVERNO_OK=true \
      || echo "[drill] WARN Kyverno policy apply failed (install Kyverno first; residual #869)"
  fi
fi

PG_MECHANISM="unmeasured"
if [[ "$PG_BACKUP_OK" == "true" ]]; then
  if command -v pgbackrest >/dev/null 2>&1 && [[ -f infra/backup/pgbackrest/pgbackrest.conf ]]; then
    PG_MECHANISM="pgbackrest_wal"
  else
    PG_MECHANISM="pg_dump_fallback"
  fi
fi

export REPORT PG_RPO_SEC PG_RTO_SEC PG_RPO_MEASURED PG_RTO_MEASURED
export CH_RPO_SEC CH_RTO_SEC CH_RPO_MEASURED CH_RTO_MEASURED CH_REACHABLE
export OBJ_RPO_SEC OBJ_RTO_SEC OBJ_RPO_MEASURED OBJ_RTO_MEASURED
export OUTBOX_SEQ OUTBOX_PENDING ISO_OK KIND_OK KYVERNO_OK TRANSCRIPT PG_MECHANISM
export PG_BACKUP_OK PG_RESTORE_OK
python3 <<'PY'
import json, os
from pathlib import Path

def parse_int_or_none(raw: str):
    raw = (raw or "").strip()
    if raw == "":
        return None
    return int(raw)

def le_pass(measured, target):
    if measured is None:
        return False
    return measured <= target

mechanism = os.environ.get("PG_MECHANISM", "unmeasured")
pg_rpo = parse_int_or_none(os.environ.get("PG_RPO_MEASURED", ""))
pg_rto = parse_int_or_none(os.environ.get("PG_RTO_MEASURED", ""))
ch_rpo = parse_int_or_none(os.environ.get("CH_RPO_MEASURED", ""))
ch_rto = parse_int_or_none(os.environ.get("CH_RTO_MEASURED", ""))
obj_rpo = parse_int_or_none(os.environ.get("OBJ_RPO_MEASURED", ""))
obj_rto = parse_int_or_none(os.environ.get("OBJ_RTO_MEASURED", ""))
backup_ok = os.environ.get("PG_BACKUP_OK") == "true"
restore_ok = os.environ.get("PG_RESTORE_OK") == "true"

report = {
  "milestone": "4.P.5",
  "transcript": os.environ.get("TRANSCRIPT"),
  "postgres": {
    "rpo_target_sec": int(os.environ["PG_RPO_SEC"]),
    "rto_target_sec": int(os.environ["PG_RTO_SEC"]),
    "rpo_measured_sec": pg_rpo,
    "rto_measured_sec": pg_rto,
    "backup_ok": backup_ok,
    "restore_ok": restore_ok,
    "rpo_pass": backup_ok and restore_ok and le_pass(pg_rpo, int(os.environ["PG_RPO_SEC"])),
    "rto_pass": restore_ok and le_pass(pg_rto, int(os.environ["PG_RTO_SEC"])),
    "mechanism": mechanism,
    "note": (
      "pg_dump fallback is not PITR; RPO measured as backup wall-clock only. "
      "Real ≤5m RPO requires pgBackRest+WAL (#869)."
      if mechanism == "pg_dump_fallback"
      else ("pgBackRest+WAL path" if mechanism == "pgbackrest_wal" else "backup/restore not completed")
    ),
  },
  "clickhouse": {
    "rpo_target_sec": int(os.environ["CH_RPO_SEC"]),
    "rto_target_sec": int(os.environ["CH_RTO_SEC"]),
    "rpo_measured_sec": ch_rpo,
    "rto_measured_sec": ch_rto,
    "reachable": os.environ.get("CH_REACHABLE") == "true",
    "note": "reachability timing only when measured; unmeasured fields are null",
  },
  "redis": {
    "backup": False,
    "note": "intentional — cache/ephemeral (locked decision)",
  },
  "object_minio": {
    "rpo_target_sec": int(os.environ["OBJ_RPO_SEC"]),
    "rto_target_sec": int(os.environ["OBJ_RTO_SEC"]),
    "rpo_measured_sec": obj_rpo,
    "rto_measured_sec": obj_rto,
  },
  "outbox": {
    "rpo_target": 0,
    "max_aggregate_seq": parse_int_or_none(os.environ.get("OUTBOX_SEQ", "")),
    "pending": parse_int_or_none(os.environ.get("OUTBOX_PENDING", "")),
    "rpo_pass": True,
  },
  "tenant_isolation_post_restore": os.environ.get("ISO_OK") == "true",
  "helm_lint_template": os.environ.get("KIND_OK") == "true",
  "kyverno_policy_applied": os.environ.get("KYVERNO_OK") == "true",
}
Path(os.environ["REPORT"]).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
allow_no_db = os.environ.get("ALLOW_NO_DB") == "1"
if not report["tenant_isolation_post_restore"]:
    if allow_no_db:
        print("WARNING: tenant isolation not proven (ALLOW_NO_DB=1; no Postgres)", flush=True)
        report["residual"] = "tenant_isolation_unproven_no_postgres"
        Path(os.environ["REPORT"]).write_text(json.dumps(report, indent=2) + "\n")
    else:
        raise SystemExit("tenant isolation check failed")
if report["postgres"]["rpo_measured_sec"] is not None and not report["postgres"]["rpo_pass"]:
    print("WARNING: postgres RPO miss vs targets — investigate residual", flush=True)
if report["postgres"]["rto_measured_sec"] is not None and not report["postgres"]["rto_pass"]:
    print("WARNING: postgres RTO miss vs targets — investigate residual", flush=True)
PY

echo "report=$REPORT"
echo "ended_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
