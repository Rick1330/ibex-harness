# PITR evidence — Stage 2 / P0-10

Artifacts in this directory were produced by a **real** point-in-time restore against the
`v1-single-node` profile (pgBackRest + S3 repository + continuous WAL archiving), not by
`ALLOW_NO_DB=1` and not by the `pg_dump` fallback.

> **Status: superseded — regenerate before citing it as RPO evidence.** `pitr-report.json` was written before the
> archive-queue check existed, so it does not record whether the archive was drained when the freshness number was
> sampled (`wal_archive_backlog` is absent). `assert_honest` now rejects that report for an RPO claim, because an upload
> age is only an upper bound on the lag while nothing older is still queued. The restore, the recovery point and the
> restored data it proves are unchanged; only the RPO claim is unverifiable from this file. Regenerate it with
> `make v1-pitr TARGET=… SCRATCH_VOLUME=… PITR_REPORT=engineering/evidence/pitr/pitr-report.json` against the same
> profile. Until then, cite this file for the restore and the target, not for the RPO.

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

**The freshness number is measured before the restore, not before the backup.** The sequence below is
`make v1-backup` → forced WAL switch and archival → `make v1-pitr`, and `pgbackrest-restore.sh` samples
`pg_stat_archiver` during that last command. A before-backup measurement is **not** captured here: it would need a
separate observation recorded before `make v1-backup`, and no such observation exists in this artefact. Read
`rpo_measured_sec` as "how stale the newest recoverable segment was when the restore started", which is the number the
RPO claim is graded on, and not as "how stale it was when the backup was taken".

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
| WAL archiving was working, read at the start of the **restore** | `postgres.wal_archive_ok` | `true` |
| The newest archive upload was 17 s old when the restore started | `postgres.rpo_measured_sec` | `17` (target 300) |
| The requested recovery point | `postgres.target_timestamp` | `2026-11-16T07:42:48Z` |
| Recovery stopped at or before it | `postgres.recovery_target_reached`, `recovery_replay_timestamp` | `true`, `2026-11-16T07:42:42Z` |
| The restored cluster held real data | `postgres.cluster_data_bytes`, `restored_row_counts` | 12,221,463 bytes, 2 organizations, 9 memories |
| RPO inside the 5-minute target, by that measurement | `postgres.rpo_pass` | `true` — not citable until regenerated (see the status note) |

A report written by the current writer also carries `wal_archive_upload_age_sec` and `wal_archive_backlog`. This
artefact predates both, so the queue state behind its `17` is not recorded; that is what the status note above means by
"regenerate before citing it as RPO evidence".

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
- **No steady-state RPO.** `rpo_measured_sec: 17` is the age of the newest archive upload when the restore started,
  not a distribution. `archive_timeout=60` bounds it on an idle cluster; a sustained-write measurement is a different
  experiment.
- **The number is an upper bound, not the frontier itself.** `last_archived_time` records when an upload *completed*,
  not the transaction time the segment carried. It bounds the RPO only while the archive queue is drained, which is why
  a regenerated report records `wal_archive_backlog` beside it and why `rpo_pass` is refused when the queue is not
  drained: a backlog draining after an outage would otherwise make old data look freshly recoverable. This artefact does
  not record that state, so its RPO claim is the one thing in it that cannot be re-verified from the file.
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
