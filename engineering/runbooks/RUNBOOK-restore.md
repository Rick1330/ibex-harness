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

Nothing in this section is destructive and nothing here restores. It resolves
and proves the values the restore will use, so the runbook runs in this order:
**stop writes → preserve incident evidence → verify the repository and the
chosen backup → restore**. The restore command appears only in
[Recovery](#recovery), after the first three steps.

1. Confirm a usable backup exists before you destroy anything. Run this from the
   repository root and **resolve the config to an absolute path**, then export it
   with the stanza the restore reads:

   ```bash
   # Docker bind-mount sources must be absolute (pgbackrest-restore.sh:142). A
   # relative value here fails after PostgreSQL is already stopped (:110-115).
   export PGBACKREST_CONF="${PGBACKREST_CONF:-$(realpath infra/backup/pgbackrest/pgbackrest.conf)}"
   export PGBACKREST_STANZA="${PGBACKREST_STANZA:-ibex-main}"
   if [[ "$PGBACKREST_CONF" != /* ]]; then
     echo "PGBACKREST_CONF must be an absolute path: $PGBACKREST_CONF" >&2
   else
     printf 'CONF=%s\nSTANZA=%s\n' "$PGBACKREST_CONF" "$PGBACKREST_STANZA"
   fi
   ```

   **Why a conditional and not shell termination.** This block is pasted into
   the operator's interactive recovery shell. The earlier `case` form terminated
   that shell on a bad value and discarded the exported values, leaving the
   operator in a fresh shell, mid-incident, with no selection; a bare `return 1`
   outside a function only prints an error and works only if the operator
   remembers to source the block. The `if` form above is safe pasted at a
   top-level prompt: it needs no function, no sourced file, and no `set -e`, and
   on a bad value it prints the reason and skips the dependent command without
   ending the shell. Every later command that depends on these values uses the
   same shape.

   **Why absolute.** `pgbackrest-restore.sh` stops PostgreSQL first
   (`:110-115`), then bind-mounts the config into the restore container as
   `-v "${CONF}:/etc/pgbackrest/pgbackrest.conf:ro"` (`:142`). Docker requires an
   absolute bind-mount source; a relative `PGBACKREST_CONF` is resolved against
   an unknown host directory and the mount fails with the database already down,
   turning a recoverable incident into an outage. The wrapper's own default is
   already absolute (`infra/scripts/dev-tool.sh`:557); only a relative value the
   operator supplies breaks it. For a **custom** config, pass an absolute path
   yourself — `realpath /path/to/custom.conf`. The check proves the *form* of the
   path, not that the file exists: GNU `realpath` resolves a missing final
   component without error, so existence is proven by the in-container repository
   check in [Recovery](#recovery) step 1 succeeding (and the wrapper refuses a
   missing file before the restore starts, `infra/scripts/dev-tool.sh`:556-580).
   In a fresh checkout the default resolves to
   `infra/backup/pgbackrest/pgbackrest.conf`, which exists only after you copy
   the shipped `.example`; the repository check failing there is the correct
   stop.

   `pgbackrest-restore.sh` resolves the repository config from `PGBACKREST_CONF`
   and falls back to `infra/backup/pgbackrest/pgbackrest.conf`, and reads the
   stanza from `PGBACKREST_STANZA` with the default `ibex-main`
   (`pgbackrest-restore.sh`:7-23,101-102). The `pgbackrest` binary reads neither
   variable, so both must be set in the shell as above: unset, the check queries
   the binary's default config and stanza, which is not necessarily the
   repository and stanza `make v1-restore` will use. A set `PGBACKREST_CONF` is
   honoured only when the file exists, and the wrapper refuses the shipped
   `.example` (`pgbackrest-restore.sh`:8-25;
   `infra/scripts/dev-tool.sh`:556-580).

   **Stop condition.** If the guard prints `PGBACKREST_CONF must be an absolute
   path`, **stop** and resolve the value again (`realpath /path/to/custom.conf`);
   do not carry a relative path into the restore. Do not continue to the
   repository check with a value you have not proven absolute.
2. Confirm the selection is the one the restore will carry. The restore command
   itself is [Recovery](#recovery) step 4 and is **not** run here. Compare the
   printed `CONF=` and `STANZA=` lines with the values you will pass on that
   `make v1-restore` line: the same absolute path, byte for byte, and the same
   stanza.

   The `v1-restore` recipe itself is `@"$(BASH)" "$(DEV_TOOL)" v1 restore`
   (`Makefile`:224-225) and does **not** name either variable, so the values
   reach `dev-tool.sh` only because GNU make exports command-line variable
   assignments into the recipe environment; `v1_restore` then runs
   `pgbackrest-restore.sh` with its environment inherited
   (`infra/scripts/dev-tool.sh`:597-600), and `resolve_conf` reads
   `PGBACKREST_CONF` (`pgbackrest-restore.sh`:101). That is why the values are
   written out here rather than assumed: nothing between `make` and the script
   re-reads or defaults them.

   **Stop condition.** If a printed value is empty, is relative, or does not
   match the `make v1-restore` line you will run, **stop** — do not restore,
   re-resolve the value, and re-run this check. A restore that reads a different
   repository or stanza than the one you verified restores a different backup
   over PostgreSQL.
3. Confirm the compose volume resolves. The restore stops Postgres through
   Compose and resolves the named volume from Compose metadata, failing closed
   if it cannot (`pgbackrest-restore.sh`:27-77).

## First response

1. Declare the incident and open the incident note.
2. Stop writes to the profile (scale the API, proxy and workers down) so the
   loss does not grow while you prepare.
3. Preserve incident evidence **before** the repository check and the restore:
   copy the current data directory, or a `pg_dump` of it, to an evidence location
   the restore will not overwrite. Do not register it as a repository backup.

   Do **not** create a backup from the readable database: a backup taken now
   captures the corrupted or partially lost state and can become the "latest" the
   restore selects, overwriting the evidence you need.

## Recovery

**Sequence: verify the repository → inspect and confirm the backup → restore.**
Do not run a later step if an earlier one fails, and do not skip to the restore.

1. **Check the repository inside the container and network the restore uses.**
   `repo1-s3-endpoint=minio:9000`
   (`infra/backup/pgbackrest/pgbackrest.conf.example`:9) resolves only on the
   Compose network, so a host-side `pgbackrest info` fails on name resolution for
   a reason that is not the repository's state. This mirrors the restore
   invocation (`pgbackrest-restore.sh`:79-98,136-146) — same image, network,
   config mount, `--config` and `--stanza` — but mounts no data volume: `info`
   renders the stanza and its `db (current)` section from the repository's
   `backup.info`, not from `PGDATA`, and not mounting the volume means this check
   cannot modify it:

   ```bash
   if [[ "$PGBACKREST_CONF" != /* ]]; then
     echo "PGBACKREST_CONF must be an absolute path: $PGBACKREST_CONF" >&2
   else
     COMPOSE_FILE=infra/compose/v1-single-node/compose.yml
     CID="$(docker compose -f "$COMPOSE_FILE" ps -q minio 2>/dev/null || true)"
     if [[ -z "$CID" ]]; then
       CID="$(docker compose -f "$COMPOSE_FILE" ps -aq 2>/dev/null | head -n1 || true)"
     fi
     NETWORK="$(docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$CID" | head -n1 | tr -d '\r')"
     docker run --rm \
       --network "$NETWORK" \
       -v "${PGBACKREST_CONF}:/etc/pgbackrest/pgbackrest.conf:ro" \
       -e PGBACKREST_REPO1_CIPHER_PASS \
       "${PGBACKREST_IMAGE:-pgbackrest/pgbackrest:2.53}" \
       pgbackrest --config=/etc/pgbackrest/pgbackrest.conf \
         --stanza="$PGBACKREST_STANZA" info
   fi
   ```

   **Stop condition.** If the guard prints `PGBACKREST_CONF must be an absolute
   path`, the network lookup finds no container or no network, the container
   exits non-zero, or `info` reports a stanza or repository you did not expect,
   **stop**: do not restore. There is no restore without a verified, reachable
   repository.
2. **Inspect and confirm the selected backup** from that `info` output. Choose a
   set whose timestamp precedes the incident, with a last-completed label you can
   name in the incident note. If you cannot establish which backup is known-good
   — no unambiguous pre-incident set, or `info` cannot confirm the repository —
   **stop** and escalate. Do not restore "the latest" hoping it is correct.
3. **Confirm the values reach the restore process.** Print what the `make` line
   will carry:

   ```bash
   printf 'CONF=%s\nSTANZA=%s\n' "$PGBACKREST_CONF" "$PGBACKREST_STANZA"
   ```

   **Stop condition.** If either line is empty, is relative, or names a different
   config path or stanza than the `info` output in step 1, **do not run the
   restore**. `v1-restore` takes these values from its environment and, absent
   them, silently falls back to the wrapper's defaults
   (`pgbackrest-restore.sh`:7-23,101-102;
   `infra/scripts/dev-tool.sh`:556-580,901), so a mismatch means it would restore
   a different backup over PostgreSQL.
4. **Restore the latest backup**, with exactly those values on the command line:

   ```bash
   if [[ "$PGBACKREST_CONF" != /* ]]; then
     echo "PGBACKREST_CONF must be an absolute path: $PGBACKREST_CONF" >&2
   else
     make v1-restore PGBACKREST_CONF="$PGBACKREST_CONF" PGBACKREST_STANZA="$PGBACKREST_STANZA"
   fi
   ```

   `make v1-restore` forwards to `dev-tool.sh v1 restore`, which first requires a
   real pgBackRest config and then runs `pgbackrest-restore.sh`
   (`infra/scripts/dev-tool.sh`:597-600,901; `Makefile`:224-225). The script
   stops Postgres, runs `pgbackrest restore` inside the compose network, and
   prints `[restore] ok <timestamp>` on success
   (`pgbackrest-restore.sh`:134-150).

   **Stop condition.** If the restore command on your line differs from the
   values verified in steps 1 and 3, **do not run it**; a relative config path
   fails inside Docker after PostgreSQL is already stopped
   (`pgbackrest-restore.sh`:110-115,142).

**Point-in-time restore is not available yet.** `make v1-pitr` with a
`TARGET=2026-11-14T03:00:00Z` **refuses** because `pgbackrest-restore.sh` has no
`--type=time` / `--target` support (no `PGBACKREST_RESTORE_TARGET` pass-through
either). The wrapper probes the script and exits non-zero rather than run a
latest restore and label it PITR (`infra/scripts/dev-tool.sh`:605-625). Do not
work around it by editing the script during an incident; a PITR restore is a
code change plus a drill, not a runtime toggle. If support is added, resolve and
carry the same values explicitly: the config must be the absolute path from
[Detection and preconditions](#detection-and-preconditions) step 1 and the stanza
the one you verified, passed on the `make v1-pitr` line as
`PGBACKREST_CONF="$PGBACKREST_CONF" PGBACKREST_STANZA="$PGBACKREST_STANZA"`, with
the repository check and value comparison re-run first (Recovery steps 1 and 3) —
because it resolves the same config and stanza through the same wrapper
(`infra/scripts/dev-tool.sh`:605-625). A relative
`PGBACKREST_CONF` fails there for the same Docker bind-mount reason as
`v1-restore` (`pgbackrest-restore.sh`:142).

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

- The in-container `pgbackrest info` output from Recovery step 1 and the chosen
  backup label/set.
- The full restore transcript, including the `[restore] ok` line.
- `restore-drill-report.json` and `transcript.txt` from the drill
  (`infra/scripts/platform/restore-drill.sh`:10-12), with `rto_pass`,
  `rpo_pass` and the fixture row count.
- The post-restore `/ready` bodies and the replay assertions above.
