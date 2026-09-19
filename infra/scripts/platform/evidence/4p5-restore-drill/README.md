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
- `kyverno_policy_applied` is **false** until staging/kind soak: #869.
- Never attach reports produced with `ALLOW_NO_DB=1` (script prints `NOT_EVIDENCE`).
