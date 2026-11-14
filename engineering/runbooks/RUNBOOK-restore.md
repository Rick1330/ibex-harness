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

1. Confirm a usable backup exists before you destroy anything. Run this from the
   repository root, and **export** the same config and stanza the restore reads.
   An unexported shell variable is invisible to `make v1-restore`, which runs as
   a separate process and would fall back to the wrapper's own defaults:

   ```bash
   export PGBACKREST_CONF="${PGBACKREST_CONF:-infra/backup/pgbackrest/pgbackrest.conf}"
   export PGBACKREST_STANZA="${PGBACKREST_STANZA:-ibex-main}"
   pgbackrest --config="$PGBACKREST_CONF" --stanza="$PGBACKREST_STANZA" info
   ```

   `pgbackrest-restore.sh` resolves the repository config from `PGBACKREST_CONF`
   and falls back to `infra/backup/pgbackrest/pgbackrest.conf`, and reads the
   stanza from `PGBACKREST_STANZA` with the default `ibex-main`
   (`pgbackrest-restore.sh`:7-23,101-102). The `pgbackrest` binary reads neither
   variable, so both must be set in the shell as above: unset, `info` queries the
   binary's default config and stanza, which is not necessarily the repository and
   stanza `make v1-restore` will use. A set `PGBACKREST_CONF` is honoured only when
   the file exists, and the wrapper refuses the shipped `.example`
   (`pgbackrest-restore.sh`:8-25; `infra/scripts/dev-tool.sh`:556-580).
2. Confirm the selection reaches the restore process, not only `info`. The same
   values must be visible to `make v1-restore`; either export them as in step 1
   and leave them exported, or pass them explicitly on the `make` command line.
   Check what will be inherited right before restoring:

   ```bash
   env | grep '^PGBACKREST_'        # after the export in step 1
   make -n v1-restore PGBACKREST_CONF=... PGBACKREST_STANZA=...   # echoed recipe
   ```

   **Stop condition.** The config and stanza the restore will use must be
   byte-identical to the ones `info` inspected in step 1. If `env` shows nothing,
   shows a different path or stanza, or you cannot say which values `make` will
   pass through, **stop and re-export** — do not restore. A restore that reads a
   different repository or stanza than the one you verified restores a different
   backup over PostgreSQL.
3. Confirm the repository is reachable. The backup/restore scripts expect an
   S3/MinIO-backed repository (`infra/scripts/platform/pgbackrest-backup.sh`:1-2).
   If `repo1-s3` is unreachable, there is no restore.
4. Confirm the compose volume resolves. The restore stops Postgres through
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
# The restore runs as a child process: export, or pass on the make line below.
export PGBACKREST_CONF="${PGBACKREST_CONF:-infra/backup/pgbackrest/pgbackrest.conf}"
export PGBACKREST_STANZA="${PGBACKREST_STANZA:-ibex-main}"
pgbackrest --config="$PGBACKREST_CONF" --stanza="$PGBACKREST_STANZA" info
env | grep '^PGBACKREST_'              # must match what info just inspected
make v1-restore                        # restores the latest backup into the profile
# Equivalent, if you prefer not to rely on the export:
# make v1-restore PGBACKREST_CONF="$PGBACKREST_CONF" PGBACKREST_STANZA="$PGBACKREST_STANZA"
```

**Stop condition.** If `env` is empty, or names a different config path or stanza
than the `info` output above, **do not run the restore**. Re-export and re-run
`info`: `make v1-restore` reads `PGBACKREST_CONF` and `PGBACKREST_STANZA` from
its environment and silently falls back to the wrapper's defaults when they are
absent (`pgbackrest-restore.sh`:7-23,101-102; `infra/scripts/dev-tool.sh`:556-580),
so a mismatch means it would restore a different backup over PostgreSQL.

Do **not** create a backup from the readable database before restoring. A backup
taken now captures the corrupted or partially lost state and can become the
"latest" the restore selects, overwriting the evidence you need. Instead:

1. Identify a known-good backup from `pgbackrest info`: a set whose timestamp
   precedes the incident, with a stuck/last-completed label you can name in the
   incident note.
2. Preserve incident evidence separately — copy the current data directory or a
   `pg_dump` to an evidence location the restore will not overwrite. Do not
   register it as a repository backup.
3. If you cannot establish which backup is known-good (no unambiguous
   pre-incident set, or `info` cannot confirm the repository), **stop** and
   escalate. Do not restore "the latest" hoping it is correct.

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
runtime toggle. If support is added, invoke it in the same exported shell as
`v1-restore` — export `PGBACKREST_CONF` and `PGBACKREST_STANZA` (or repeat them
on the `make v1-pitr` line) and re-run the step-2 check — because it resolves
the same config and stanza through the same wrapper
(`infra/scripts/dev-tool.sh`:605-625).

**After a restore:**

1. **Start PostgreSQL alone; leave ingress closed.** The restore stops Postgres
   and leaves it stopped (`pgbackrest-restore.sh`:110-115). Bring up only the
   database through the profile's own service control, which also selects the
   container runtime and the profile env file:

   ```bash
   bash infra/scripts/dev-tool.sh v1 up --no-build postgres
   ```

   That resolves to `compose_with_mode v1 up -d --no-build postgres`
   (`infra/scripts/dev-tool.sh`:627-644) over the profile's Compose file, env file
   and container runtime (`infra/scripts/dev-tool.sh`:74-106), so Compose starts
   `postgres` and its dependencies only: `postgres` declares none
   (`infra/compose/v1-single-node/compose.yml`:22-38). Every application service
   gates on the `migrate`, `provision` and `bootstrap` one-shots or on another
   service (`compose.yml`:57-147,182-188,232-240), and the only published port is
   the edge terminator (`compose.yml`:511-537). Confirm with `make v1-ps`
   (`Makefile`:215-216) that `postgres` is running and no application service is.
   Do not run `make v1-up` yet: it starts the whole profile and then the smoke
   request (`Makefile`:174-196), which reopens traffic.
2. **Check the restored data against the replay contract.** The restore-replay
   integration test states what a restored copy must satisfy: the memory is a
   tombstone (`content = '[forgotten]'`, `status = 'deleted'`,
   `tombstoned = TRUE`), exactly one `forgotten/2` lifecycle-outbox marker
   exists, the deletion receipt has `verified_absent_at` set, the idempotency
   ledger holds the erased marker `{"erased": true}`, and the content is not
   resurrected — the test first proves a pre-forget restore *does* resurrect it,
   so the assertion discriminates
   (`infra/migrations/postgres/restore_replay_integration_test.go`:1-30,61,549-559,567-581,594-647).
   Query the restored database while traffic is still blocked and compare against
   that contract. If the restored data resurrects content, **do not start the
   profile**: keep traffic blocked and escalate. A restore that brings deleted
   content back is an incident, not a completed recovery.
3. **Establish what should be absent from a source outside the restored
   database.** The markers in step 2 were restored from the same backup, so they
   prove the copy is self-consistent, not that it is complete; and the
   integration test's sentinel
   (`restore_replay_integration_test.go`:61) is a test-database fixture, not
   production evidence. Before serving traffic, obtain the set of production
   content deleted after the backup from a record the restore cannot rewrite:
   the erasure and deletion request/job records the operator holds, a deletion
   evidence export taken from the live system before the restore, or a receipt or
   audit copy kept outside this database. A receipt in
   `ibex_core.deletion_store_receipts` is a row of the database being restored
   (`infra/migrations/postgres/000037_privacy_governance.up.sql`:354), so it is
   not that record, and neither is anything else inside the restored copy. Where
   the profile enables no such store, that record is the operator's — the
   ClickHouse projection is a default-off, non-production pilot
   (`engineering/adr/0085-evidence-relay-daemon-and-session-fence.md`:60), so do
   not assume it. Check each of those identifiers in the restored database and
   confirm it is absent or tombstoned. If the independent record cannot be
   produced or checked, **keep traffic blocked and escalate**: an unverified
   restore is not a recovery. Never present the in-database markers or the test
   sentinel as that record.
4. A restored provider credential must decrypt under the recovered
   `IBEX_CREDENTIALS_MASTER_KEY`; if it does not, use the master-key runbook
   (`engineering/runbooks/RUNBOOK-master-key.md`).
5. Only after steps 1–4 pass, start the profile (`make v1-up`) and confirm
   `/ready` on each service.

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
