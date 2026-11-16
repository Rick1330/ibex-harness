# PITR evidence — Stage 2 / P0-10

Artifacts in this directory were produced by a **real** point-in-time restore against the
`v1-single-node` profile (pgBackRest + S3 repository + continuous WAL archiving), not by
`ALLOW_NO_DB=1` and not by the `pg_dump` fallback.

> **Status: citable for the restore and the target; it carries no RPO claim, and cannot.** This artefact is a
> **targeted** rehearsal (`TARGET=2026-11-16T07:42:48Z`) whose restored cluster replayed to `2026-11-16T07:42:42Z`.
> A targeted restore proves that the target was reached, not an RPO: it stops where the operator asked, so the 6 s
> between the replay and the target is the target offset, not archive lag. The artefact records **no quiesce instant**
> (`wal_archive_quiesced_at: null`): the scratch path stops nothing, so no instant at which archiving stopped was
> measured, and **no RPO bound is derivable from it**. The report therefore records `rpo_upper_bound_sec: null`,
> `rpo_pass: false` and `postgres_rpo_residual: "targeted_restore_proves_target_not_rpo"`, and stays
> `evidence_eligible` for what it did prove. The historical `rpo_measured_sec: 17` was an upload age read from
> `pg_stat_archiver`, not a frontier, so it was removed rather than renamed. An RPO upper bound needs an untargeted
> restore plus two measured instants (`wal_archive_quiesced_at`, `recovery_replay_timestamp`); regenerate with an
> untargeted run if you need one.

| File | Purpose |
|---|---|
| `pitr-report.json` | The report `make v1-pitr` wrote for this run |
| `pitr-run-transcript.txt` | Verbatim stdout of the run, including the printed next step. It shows the report as the run wrote it, **before** the amendment described above, so its JSON block carries stale claims: `rpo_measured_sec: 17`, `rpo_pass: true` and `tenant_isolation_post_restore: false`. The run was targeted, so the first two are not claimable today — the 17 was an upload age, not a frontier, and a targeted run never carries an RPO pass. The third is worse than stale: under the tri-state `false` means a **measured isolation failure**, which the writer now refuses, while the scratch path runs no cross-tenant check at all. It should read `null` (not measured), which is what the amended artefact carries. Do not cite any of the three as current |

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

**The freshness number in the transcript is an upload age, not a frontier.** The sequence below is
`make v1-backup` → forced WAL switch and archival → `make v1-pitr`, and `pgbackrest-restore.sh` samples
`pg_stat_archiver` during that last command. The `newest_archived_age_sec=17` line is how old the newest archive upload
was at that moment. It is a diagnostic: an upload age bounds nothing on its own, which is why the report does not carry
it as an RPO and why no field is named after it.

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
| No RPO claim, by design | `postgres.rpo_upper_bound_sec`, `postgres_rpo_residual` | `null`, `targeted_restore_proves_target_not_rpo` — a targeted restore proves the target, not an RPO |
| The requested recovery point | `postgres.target_timestamp` | `2026-11-16T07:42:48Z` |
| Recovery stopped at or before it | `postgres.recovery_target_reached`, `recovery_replay_timestamp` | `true`, `2026-11-16T07:42:42Z` |
| The restored cluster held real data | `postgres.cluster_data_bytes`, `restored_row_counts` | 12,221,463 bytes, 2 organizations, 9 memories |
| RPO claimed | `postgres.rpo_pass` | `false` — a targeted run may never carry one |

A report written by the current writer also carries `wal_archive_upload_age_sec`, `wal_archive_timeout_sec`,
`wal_archive_wal_segment_size` and `wal_archive_backlog`. Those are diagnostics: none of them gates `rpo_pass`, and none
of them can substitute for the two instants an RPO upper bound is derived from. The committed artefact carries them as
the producer writes them: the upload age is `17`, the value this run's transcript recorded; the timeout, segment size
and backlog are `null`, because the producer that ran did not record them. They are keys with no measured value, not
plausible numbers filled in after the fact.

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
- **No RPO, and no steady-state RPO.** A targeted rehearsal cannot carry an RPO claim: it proves the target, not the
  archive lag. The bound a report may carry comes from an untargeted run, and is
  `ceil(wal_archive_quiesced_at − recovery_replay_timestamp)` — the gap between the instant the primary stopped (nothing
  new is archived after that) and the instant the restored cluster replayed to. That gap is wall-clock: it includes any
  idle time between the last write and the stop, so a quiet cluster can miss a short target with no archive fault. A
  sustained-write distribution is a different experiment, and this file does not claim one.
- **When a bound exists, the restore demonstrates it.** It is not `last_archived_time` plus `archive_timeout`, and it is not read
  from `pg_stat_archiver` at all: a push slower than `archive_timeout` leaves the counters looking drained while the
  newest recoverable commit is older than the number they would produce. The restore is the continuity proof — it
  replays every segment from the backup to the replay point, so a gap either stops recovery or truncates the replay
  timestamp, and the derived number then shows it. `wal_archive_backlog`, `wal_archive_ok` and the upload age are
  diagnostics and gate nothing.
- **No RTO.** `rto_measured_sec` is null: a PITR rehearsal does not measure detection, drain, restore and verification
  as an RTO, so the report does not invent one.
- **No tenant-isolation result.** The rehearsal never queries restored tenant data under RLS, so it records
  `tenant_isolation_post_restore: null` and `residual: "tenant_isolation_not_measured_pitr"`. `null` means "not
  measured in this run", not "measured and failed"; the drill is where isolation is proven.
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
