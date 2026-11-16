# PITR evidence — Stage 2 / P0-10

Artifacts in this directory were produced by a **real** point-in-time restore against the
`v1-single-node` profile (pgBackRest + S3 repository + continuous WAL archiving), not by
`ALLOW_NO_DB=1` and not by the `pg_dump` fallback.

| File | Purpose |
|---|---|
| `pitr-report.json` | The report `make v1-pitr` wrote for this run |
| `pitr-run-transcript.txt` | Verbatim stdout of the run, including the printed next step |

## Why this exists

The committed drill report (`infra/scripts/platform/evidence/4p5-restore-drill/restore-drill-report.json`) is
`mechanism: pg_dump_fallback` with `rpo_pass: false`, because the drill silently fell back when it could not bind to
pgBackRest. `make v1-pitr` performed a restore but wrote no report at all. Neither path could ever produce an artefact
showing a PITR mechanism, so the RPO claim was unproven **by construction** rather than by outcome.

This report is the first artefact produced by the pgBackRest WAL path. `make v1-pitr` now writes it through the same
writer the drill uses (`infra/scripts/platform/pitr_report.sh` → `restore_drill_report.py`), so the two paths cannot
drift.

## The run

Host: `DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`, `IBEX_RUNTIME=podman`, rootless podman.
Environment class recorded in the report: `local-podman-scratch`. This is a **local** result; it is not a hosted or
HA result, and the report says so.

Sequence:

```bash
# Profile data plane only (postgres + objectstore + one-shots); the rest of the
# profile is not needed to restore.
podman compose -f infra/compose/v1-single-node/compose.yml \
  --env-file infra/compose/v1-single-node/.env up -d postgres objectstore objectstore-init

make v1-backup-init            # stanza-create, idempotent
make v1-backup                 # full backup 20261116-074207F, database size 33.7MB

# A row written BEFORE the recovery target, then the target, then a row written AFTER it.
# The pair is what discriminates a real PITR from a restore of the latest backup.
#   pitr-a-20261116t074241  committed ~07:42:42Z   (before the target)
#   target                                        2026-11-16T07:42:48Z
#   pitr-b-20261116t074241  committed ~07:42:48Z   (after the target)
# WAL switched and archived so transactions after the target exist in the repository:
#   SELECT pg_switch_wal();  -> archived_count 17, last_archived_time 07:42:51Z

podman volume create ibex-pitr-scratch-p0-10
make v1-pitr TARGET=2026-11-16T07:42:48Z \
             SCRATCH_VOLUME=ibex-pitr-scratch-p0-10 \
             PITR_REPORT=engineering/evidence/pitr/pitr-report.json
```

Result (from the transcript):

```text
[restore] point-in-time target=2026-11-16 07:42:48+00 (from 2026-11-16T07:42:48Z; --type=time --target-action=promote)
[restore] wal_archive_ok=true newest_archived_age_sec=17
[restore] scratch restore ok 2026-11-16T07:43:10Z
[restore] scratch cluster verified: pg_is_in_recovery()=false
[restore] recovery target reached: replay=2026-11-16T07:42:42Z target=2026-11-16T07:42:48Z
[restore] restored cluster bytes=12221463 orgs=2 memories=9
[pitr-report] wrote engineering/evidence/pitr/pitr-report.json
```

## What the report proves

| Claim | Field | Value |
|---|---|---|
| The mechanism was pgBackRest + WAL, not a dump | `postgres.mechanism` | `pgbackrest_wal` |
| WAL archiving was working, read before the backup | `postgres.wal_archive_ok` | `true` |
| The newest archived segment was 17 s old at the start of the run | `postgres.rpo_measured_sec` | `17` (target 300) |
| The requested recovery point | `postgres.target_timestamp` | `2026-11-16T07:42:48Z` |
| Recovery stopped at or before it | `postgres.recovery_target_reached`, `recovery_replay_timestamp` | `true`, `2026-11-16T07:42:42Z` |
| The restored cluster held real data | `postgres.cluster_data_bytes`, `restored_row_counts` | 12,221,463 bytes, 2 organizations, 9 memories |
| RPO inside the 5-minute target, by that measurement | `postgres.rpo_pass` | `true` |

Row-level check on the restored volume, started separately with `archive_mode=off` after the run:

```text
in_recovery=f
pitr-a-20261116t074241 (written before the target) = 1
pitr-b-20261116t074241 (written after the target)  = 0
total organizations = 2        (live cluster: 3)
```

The row written before the target came back; the row written after it did not. That pair is the discrimination a
`pg_dump` restore cannot provide, and it is why the total is 2 rather than 3.

## What this does not claim

- **No hosted or HA result.** `environment_class` is `local-podman-scratch`. The status ledger's boundary on hosted HA
  and measured p99 SLOs is unchanged by this file.
- **No steady-state RPO.** `rpo_measured_sec: 17` is the age of the newest archived segment at the moment this run
  started, not a distribution. `archive_timeout=60` bounds it on an idle cluster; a sustained-write measurement is a
  different experiment.
- **No RTO.** `rto_measured_sec` is null: a PITR rehearsal does not measure detection, drain, restore and verification
  as an RTO, so the report does not invent one.
- **No tenant-isolation result.** The rehearsal restores into a scratch volume and never queries tenant data under
  RLS; `tenant_isolation_post_restore` is false, and the drill is where that is proven.
- **No claim about a target later than the end of archived WAL.** The first attempt at this run targeted a moment
  after the last archived transaction and PostgreSQL refused to promote (`recovery ended before configured recovery
  target was reached`). The script reported the failure, exited non-zero, and wrote a report with `restore_ok: false`.
  That failure is why the committed run writes a row **after** the target.

## Reproducing

```bash
make v1-pitr TARGET=<ISO8601 after a written row> \
             SCRATCH_VOLUME=<volume> \
             PITR_REPORT=<path>
```

`PITR_REPORT` defaults to `${RESTORE_DRILL_REPORT_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}}/ibex/restore-drill/pitr-report.json`.
Do not commit a report produced by a run whose `blocked_by` is set as if it were a PITR result: `mechanism: unavailable`
is an honest outcome, not evidence for an RPO claim.
