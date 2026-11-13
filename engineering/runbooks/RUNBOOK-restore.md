# Runbook: Restore PostgreSQL from backup (P1)

**Scope.** Restoring the `v1-single-node` PostgreSQL from a pgBackRest backup
after data loss or corruption. The restore is **destructive**: it stops
PostgreSQL and overwrites the data directory
(`infra/scripts/platform/pgbackrest-restore.sh`:110-150). Treat it as a
declared incident with an incident note, not a routine maintenance command.

## Symptoms

- Confirmed data loss or corruption in `ibex_core` (bad migration, accidental
  delete, failed host).
- `IBEXPostgresBackupStale` is firing: `ibex_postgres_last_backup_unixtime` is
  older than ~4 minutes, or absent
  (`infra/monitoring/prometheus/rules/ibex-platform-backup.yml`:5-18).
- `IBEXRestoreDrillMissing` is firing: no successful drill metric in 24 h
  (`ibex-platform-backup.yml`:20-32).
- `/ready` on the API or memory returns 503 with a Postgres dependency error.

## Detection and preconditions

1. Confirm a usable backup exists before you destroy anything:

   ```bash
   PGBACKREST_CONF=infra/backup/pgbackrest/pgbackrest.conf \
     pgbackrest --stanza=ibex-main info
   ```

   A real `pgbackrest.conf` must exist; the scripts refuse the `.example`
   (`pgbackrest-restore.sh`:10-25).
2. Confirm the repository is reachable. The backup/restore scripts expect an
   S3/MinIO-backed repository (`infra/scripts/platform/pgbackrest-backup.sh`:1-2).
   If `repo1-s3` is unreachable, there is no restore.
3. Confirm the compose volume resolves. The restore stops Postgres through
   Compose and resolves the named volume from Compose metadata, failing closed
   if it cannot (`pgbackrest-restore.sh`:27-77).

## First response

1. Declare the incident and open the incident note.
2. Stop writes to the profile (scale the API, proxy and workers down) so the
   loss does not grow while you prepare.
3. Capture the last backup timestamp and `pgbackrest info` output **before**
   restoring.

## Recovery

**Latest restore (supported):**

```bash
make v1-backup TYPE=full      # if no recent backup exists and the DB is readable
make v1-restore               # restores the latest backup into the profile
```

`make v1-restore` forwards to `dev-tool.sh v1 restore`, which first requires a
real pgBackRest config and then runs `pgbackrest-restore.sh`
(`infra/scripts/dev-tool.sh`:549-552; `Makefile`:224-225). The script stops
Postgres, runs `pgbackrest ... restore` inside the compose network, and prints
`[restore] ok <timestamp>` on success (`pgbackrest-restore.sh`:134-150).

**Point-in-time restore is not available yet.** `make v1-pitr TARGET=...`
**refuses** because `pgbackrest-restore.sh` has no `--type=time` / `--target`
support (no `PGBACKREST_RESTORE_TARGET` pass-through either). The wrapper probes
the script and exits non-zero rather than run a latest restore and label it PITR
(`infra/scripts/dev-tool.sh`:554-576). Do not work around it by editing the
script during an incident; a PITR restore is a code change plus a drill, not a
runtime toggle.

**After a restore:**

1. Start the profile (`make v1-up`) and confirm `/ready` on each service.
2. Confirm forgotten content did **not** come back. The restore-replay
   integration test is the contract: a restore must carry tombstones, the
   lifecycle-outbox marker and the deletion receipt, and the sentinel must be
   absent (`infra/migrations/postgres/restore_replay_integration_test.go`:1-30).
   A restored provider credential must also decrypt under the recovered
   `IBEX_CREDENTIALS_MASTER_KEY`; if it does not, use the master-key runbook.

## Escalation

- Escalate to infrastructure when the repository itself is unavailable or the
  backup is older than the RPO budget.
- Escalate to the owner for any request to restore to a timestamp; that is the
  open PITR row, not an operator action.

## Evidence to keep

- `pgbackrest info` and the chosen backup label/set.
- The full restore transcript, including the `[restore] ok` line.
- `restore-drill-report.json` and `transcript.txt` from the drill
  (`infra/scripts/platform/restore-drill.sh`:10-12), with `rto_pass`,
  `rpo_pass` and the fixture row count.
- The post-restore `/ready` bodies and the replay assertions above.
