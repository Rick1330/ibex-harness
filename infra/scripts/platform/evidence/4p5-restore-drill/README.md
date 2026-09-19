# 4.P.5 restore-drill evidence (Gate G5 scaffolding)

Artifacts in this directory were produced by a **real** dump → induce-loss →
restore → RLS isolation run against Postgres (not `ALLOW_NO_DB=1`).

| File | Purpose |
|---|---|
| `restore-drill-report.json` | Machine-readable pass/fail + measured timings |
| `transcript.txt` | Full stdout transcript of the drill |

## How to reproduce

```bash
# Dedicated DB + non-superuser RLS login (ibex_rls → SET LOCAL ROLE ibex_app)
RESTORE_DRILL_REPORT_DIR="$PWD/infra/scripts/platform/evidence/4p5-restore-drill" \
SKIP_COMPOSE=1 \
POSTGRES_CONTAINER=<postgres-container> \
POSTGRES_DB=ibex_drill \
POSTGRES_USER=ibex \
POSTGRES_RLS_USER=ibex_rls \
POSTGRES_RLS_PASSWORD=ibex_rls \
POSTGRES_RLS_DSN='postgres://ibex_rls:…@host:port/ibex_drill?sslmode=disable' \
bash infra/scripts/platform/restore-drill.sh
```

## Honesty notes

- `postgres.rpo_pass` is **false** for `pg_dump_fallback` (not PITR). Residual: #869.
- `postgres.rpo_measured_sec` is **null** — backup wall-clock is not RPO; WAL archive
  freshness + PITR are required before exporting a measured RPO (#869).
- `kyverno_policy_applied` is **false** until staging/kind soak: #869.
- Never attach reports produced with `ALLOW_NO_DB=1` (script prints `NOT_EVIDENCE`).

## Post-run transform record

The committed `restore-drill-report.json` is **not** a byte-identical copy of the
raw `restore_drill_report.py` stdout from the drill run. After a successful
evidence-grade run, the following normalizations were applied before commit:

1. **`transcript` path** — absolute host path rewritten to the repo-relative
   `infra/scripts/platform/evidence/4p5-restore-drill/transcript.txt`.
2. **`evidence_note`** — added to record environment (podman `ibex-test-pg`,
   database `ibex_drill`, role `ibex_rls` → `SET LOCAL ROLE ibex_app`), mechanism
   honesty, and Kyverno deferral (#869).
3. **`rpo_measured_sec`** — set to `null` when the generator had incorrectly
   exported backup wall-clock as RPO (corrected to match drill honesty: RPO
   remains unmeasured without WAL/PITR).

`transcript.txt` remains the verbatim tee of the drill stdout.
