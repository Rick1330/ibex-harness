#!/usr/bin/env bash
# Write the point-in-time restore report (Stage 2 / P0-10).
#
# `make v1-pitr` and pgbackrest-restore.sh both call this, so the artefact a
# committed report comes from is the same writer the operator sees at 03:00 and
# the two paths cannot drift. The schema and its honesty rules live in
# restore_drill_report.py; this file only maps the PITR_* variables onto it.
#
# A PITR report never advances ibex_restore_drill_last_success_unixtime: that
# gauge means "the scheduled drill succeeded", and a rehearsal must not mask a
# drill that stopped running.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

REPORT_PATH="${PITR_REPORT:-}"
if [[ -z "$REPORT_PATH" ]]; then
  echo "[pitr-report] PITR_REPORT is unset; no report path was given" >&2
  exit 2
fi
mkdir -p "$(dirname "$REPORT_PATH")"

REPORT="$REPORT_PATH" \
  TRANSCRIPT="${PITR_TRANSCRIPT:-}" \
  DRILL_KIND=pitr \
  DRILL_STARTED_AT="${PITR_STARTED_AT:-}" \
  ENVIRONMENT_CLASS="${PITR_ENVIRONMENT_CLASS:-}" \
  PG_MECHANISM="${PITR_MECHANISM:-unavailable}" \
  PG_BACKUP_OK="${PITR_BACKUP_OK:-false}" \
  PG_RESTORE_OK="${PITR_RESTORE_OK:-false}" \
  WAL_ARCHIVE_OK="${PITR_WAL_ARCHIVE_OK:-false}" \
  WAL_ARCHIVE_UPLOAD_AGE_SEC="${PITR_WAL_ARCHIVE_UPLOAD_AGE_SEC:-}" \
  WAL_ARCHIVE_LAST_SEGMENT="${PITR_WAL_ARCHIVE_LAST_SEGMENT:-}" \
  WAL_ARCHIVE_CURRENT_SEGMENT="${PITR_WAL_ARCHIVE_CURRENT_SEGMENT:-}" \
  WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE="${PITR_WAL_ARCHIVE_LAST_FAILED_AFTER_ARCHIVE:-}" \
  PG_RPO_MEASURED="${PITR_RPO_MEASURED:-}" \
  TARGET_TIMESTAMP="${PITR_TARGET_TIMESTAMP:-}" \
  RECOVERY_TARGET_REACHED="${PITR_RECOVERY_TARGET_REACHED:-}" \
  RECOVERY_REPLAY_TIMESTAMP="${PITR_RECOVERY_REPLAY_TIMESTAMP:-}" \
  CLUSTER_DATA_BYTES="${PITR_CLUSTER_DATA_BYTES:-}" \
  RESTORED_ORGS="${PITR_RESTORED_ORGS:-}" \
  RESTORED_MEMORIES="${PITR_RESTORED_MEMORIES:-}" \
  BLOCKED_BY="${PITR_BLOCKED_BY:-}" \
  ISO_OK=false \
  KIND_OK=false \
  KYVERNO_OK=false \
  IBEX_DRILL_METRICS_DISABLED=1 \
  python3 "$ROOT/infra/scripts/platform/restore_drill_report.py"
echo "[pitr-report] wrote $REPORT_PATH"
