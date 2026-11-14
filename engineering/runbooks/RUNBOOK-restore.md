# Runbook: Restore PostgreSQL from backup (P1)

**Scope.** Restoring the `v1-single-node` PostgreSQL from a pgBackRest backup
after data loss or corruption. The restore is **destructive**: it stops
PostgreSQL, reconciles the live data directory with `--delta`, starts the cluster
and proves it left recovery before printing `ok`
(`infra/scripts/platform/pgbackrest-restore.sh`:528-533,564-598,702). Treat it as a
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
   # Docker bind-mount sources must be absolute (pgbackrest-restore.sh:693). A
   # relative value here fails after PostgreSQL is already stopped (:528-533).
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
   (`:528-533`), then bind-mounts the config into the restore container as
   `-v "${CONF}:/etc/pgbackrest/pgbackrest.conf:ro"` (`:693`). Docker requires an
   absolute bind-mount source; a relative `PGBACKREST_CONF` is resolved against
   an unknown host directory and the mount fails with the database already down,
   turning a recoverable incident into an outage. The wrapper's own default is
   already absolute (`infra/scripts/dev-tool.sh`:558); only a relative value the
   operator supplies breaks it. For a **custom** config, pass an absolute path
   yourself — `realpath /path/to/custom.conf`. The check proves the *form* of the
   path, not that the file exists: GNU `realpath` resolves a missing final
   component without error, so existence is proven by the in-container repository
   check in [Recovery](#recovery) step 1 succeeding (and the wrapper refuses a
   missing file before the restore starts, `infra/scripts/dev-tool.sh`:557-581).
   In a fresh checkout the default resolves to
   `infra/backup/pgbackrest/pgbackrest.conf`, which exists only after you copy
   the shipped `.example`; the repository check failing there is the correct
   stop.

   `pgbackrest-restore.sh` resolves the repository config from `PGBACKREST_CONF`
   and falls back to `infra/backup/pgbackrest/pgbackrest.conf`, and reads the
   stanza from `PGBACKREST_STANZA` with the default `ibex-main`
   (`pgbackrest-restore.sh`:24-40,152-153). The `pgbackrest` binary reads neither
   variable, so both must be set in the shell as above: unset, the check queries
   the binary's default config and stanza, which is not necessarily the
   repository and stanza `make v1-restore` will use. A set `PGBACKREST_CONF` is
   honoured only when the file exists, and the wrapper refuses the shipped
   `.example` (`pgbackrest-restore.sh`:24-40;
   `infra/scripts/dev-tool.sh`:557-581).

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
   (`Makefile`:238-239) and does **not** name either variable, so the values
   reach `dev-tool.sh` only because GNU make exports command-line variable
   assignments into the recipe environment; `v1_restore` then runs
   `pgbackrest-restore.sh` with its environment inherited
   (`infra/scripts/dev-tool.sh`:710-714), and `resolve_conf` reads
   `PGBACKREST_CONF` (`pgbackrest-restore.sh`:24-40). That is why the values are
   written out here rather than assumed: nothing between `make` and the script
   re-reads or defaults them.

   **Stop condition.** If a printed value is empty, is relative, or does not
   match the `make v1-restore` line you will run, **stop** — do not restore,
   re-resolve the value, and re-run this check. A restore that reads a different
   repository or stanza than the one you verified restores a different backup
   over PostgreSQL.
3. Confirm the compose volume resolves. The restore stops Postgres through
   Compose and resolves the named volume from Compose metadata, failing closed
   if it cannot (`pgbackrest-restore.sh`:73-123,528-533).

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
   invocation (`pgbackrest-restore.sh`:685-696) — same image, network,
   config mount, `--config` and `--stanza` — but mounts no data volume: `info`
   renders the stanza and its `db (current)` section from the repository's
   `backup.info`, not from `PGDATA`, and not mounting the volume means this check
   cannot modify it:

   ```bash
   if [[ "$PGBACKREST_CONF" != /* ]]; then
     echo "PGBACKREST_CONF must be an absolute path: $PGBACKREST_CONF" >&2
   else
     # The generated config carries no S3 credentials, so all three values the
     # restore forwards by name must be loaded from the protected .env here too.
     # Nothing below prints a value or puts one on a command line.
     ENV_FILE="${IBEX_V1_ENV:-infra/compose/v1-single-node/.env}"
     ibex_env_value() { python3 infra/scripts/lib/dotenv.py "$1" < "$ENV_FILE"; }
     PGBACKREST_REPO1_CIPHER_PASS="$(ibex_env_value PGBACKREST_REPO1_CIPHER_PASS)"
     PGBACKREST_REPO1_S3_KEY="$(ibex_env_value IBEX_OBJECTSTORE_ACCESS_KEY)"
     PGBACKREST_REPO1_S3_KEY_SECRET="$(ibex_env_value IBEX_OBJECTSTORE_SECRET_KEY)"
     export PGBACKREST_REPO1_CIPHER_PASS PGBACKREST_REPO1_S3_KEY PGBACKREST_REPO1_S3_KEY_SECRET
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
       -e PGBACKREST_REPO1_S3_KEY \
       -e PGBACKREST_REPO1_S3_KEY_SECRET \
       "${PGBACKREST_IMAGE:-ibex-v1-postgres:local}" \
       pgbackrest --config=/etc/pgbackrest/pgbackrest.conf \
         --stanza="$PGBACKREST_STANZA" info
   fi
   ```

   The default image is the profile's own postgres image
   (`infra/scripts/dev-tool.sh`:701-708), which carries pgBackRest: there is no
   `pgbackrest/pgbackrest` repository on Docker Hub, so a preflight defaulted to
   one fails at pull time and blocks recovery. `PGBACKREST_IMAGE` still overrides
   it when a different pgBackRest build is in use.

   The stanza config intentionally carries no credentials (see
   `engineering/DEPLOYMENT.md`), so `-e PGBACKREST_REPO1_CIPHER_PASS` alone is not
   enough: the container cannot authenticate to S3 without the key pair. The
   three names above are the same three the restore script forwards to its own
   container (`pgbackrest-restore.sh`:219).

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
   (`pgbackrest-restore.sh`:24-40,152-153;
   `infra/scripts/dev-tool.sh`:557-581,1009-1010), so a mismatch means it would
   restore a different backup over PostgreSQL.
4. **Restore the latest backup**, with exactly those values on the command line:

   ```bash
   if [[ "$PGBACKREST_CONF" != /* ]]; then
     echo "PGBACKREST_CONF must be an absolute path: $PGBACKREST_CONF" >&2
   else
     make v1-restore PGBACKREST_CONF="$PGBACKREST_CONF" PGBACKREST_STANZA="$PGBACKREST_STANZA"
   fi
   ```

   `make v1-restore` forwards to `dev-tool.sh v1 restore`, which first requires a
   real pgBackRest config, exports the repository credentials from the profile's
   `0600` `.env`, and then runs `pgbackrest-restore.sh`
   (`infra/scripts/dev-tool.sh`:607-610,710-714; `Makefile`:238-239). The script
   stops Postgres (`pgbackrest-restore.sh`:528-533), resolves the live volume from
   Compose metadata (`:535-541`), and runs `pgbackrest restore` inside the compose
   network with `--delta` (`:685-696`). `--delta` is not optional: pgBackRest
   refuses a non-empty `pg1-path` and the live data directory is non-empty by
   definition, so without it the command would abort after Postgres is already
   stopped (`:197-205`). The script then proves the restore before reporting it:
   `PG_VERSION` exists on the volume (`:566-571`), Postgres starts (`:573`),
   and `pg_is_in_recovery()` is false (`:582-595`). It prints
   `[restore] ok <timestamp>` only after that proof (`:702`) and **leaves the
   cluster running and verified**.

   **Stop condition.** If the restore command on your line differs from the
   values verified in steps 1 and 3, **do not run it**; a relative config path
   fails inside Docker after PostgreSQL is already stopped
   (`pgbackrest-restore.sh`:528-533,693).

**Point-in-time restore is destructive and supported.** `make v1-pitr
TARGET=2026-11-14T03:00:00Z` restores to that moment. `dev-tool.sh v1 pitr`
requires the target, exports it as `PGBACKREST_RESTORE_TARGET`, and runs the same
script (`infra/scripts/dev-tool.sh`:719-732; `Makefile`:241-242). The script
validates the value as ISO-8601 and normalises it to the shape pgBackRest's
`--target` parser accepts — the `T` separator becomes a space and a `Z` suffix
becomes `+00`, because pgBackRest rejects both (`pgbackrest-restore.sh`:171-190) —
then restores with `--type=time --target=<normalised> --target-action=promote`
(`:192-195`). It takes the same destructive path as `v1-restore`: stop Postgres,
`--delta`, `PG_VERSION` before the server starts, and `pg_is_in_recovery()=false`
before `ok` (`:197-205,528-533,564-598,702`). On success it also leaves the cluster
running and verified.

**Rehearse on a scratch volume first.** `make v1-pitr TARGET=… SCRATCH_VOLUME=<name>`
restores beside the live cluster into a separate volume and stops nothing: the
script takes the scratch branch, restores without `--delta` because that volume is
empty, prints the start command for the restored copy, and exits without mounting
the live data directory (`pgbackrest-restore.sh`:11-13,477-510;
`Makefile`:241-242). Create the volume first (`docker volume create <name>` or
`podman volume create <name>`). This is the recommended first rehearsal for any
target you intend to use in an incident, and the only way to prove a timestamp
without destroying the running database. The scratch copy is left **stopped**: the
script prints the command that starts it with `archive_mode=off`, so the restored
timeline cannot write into the live repository (`:501-504`).

**Credentials never go on a command line.** `make v1-restore` and `make v1-pitr`
export `PGBACKREST_REPO1_CIPHER_PASS`, `PGBACKREST_REPO1_S3_KEY` and
`PGBACKREST_REPO1_S3_KEY_SECRET` from the profile's `0600` `.env`
(`infra/scripts/dev-tool.sh`:607-610; `infra/scripts/gen-v1-secrets.sh`:527-544). The
script writes them to a `0600` file created with `mktemp` and hands that file to
the engine with `--env-file`, removing it on exit
(`pgbackrest-restore.sh`:317-398). It does not use `-e VAR`: with a rootful
engine (`IBEX_PODMAN_SUDO=1` makes the engine `sudo -n podman`) sudo's
`env_reset` discards the exported values, and a name-only `-e` then reaches the
container empty — after Postgres has already been stopped. The script also proves
delivery *before* that point by starting a probe container the same way and
failing if any value is missing or altered
(`pgbackrest-restore.sh`:422-437,524-526), so a delivery failure leaves the
database running. A direct invocation with `COMPOSE_FILE` pointing at the v1
profile and nothing exported loads the same three values from the profile `.env`
itself (`:265-295`). Read the values from the file; do
not paste a credential into a shell command, where a process listing would
expose it.

**After a restore:**

1. **PostgreSQL is already running and verified; leave the rest of the profile
   down.** Both destructive paths stop Postgres, restore, start it, and require
   `pg_is_in_recovery()=false` before printing `ok`
   (`pgbackrest-restore.sh`:528-533,564-598,702). They do **not** stop the
   application services, which is why [First response](#first-response) step 2
   stops them before the restore starts. Confirm with `make v1-ps`
   (`Makefile`:226-227) that `postgres` is running and no application service is.
   Do not run `make v1-up` yet: it starts the whole profile and then the smoke
   request (`Makefile`:174-206), which reopens traffic.
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
- Escalate to the owner when the recovery target is not established from a record
  the restore cannot rewrite. `make v1-pitr` will restore to any timestamp you
  give it; choosing that timestamp for an incident is the owner's decision, not a
  default the operator infers from the latest backup.

## Evidence to keep

- The in-container `pgbackrest info` output from Recovery step 1 and the chosen
  backup label/set.
- The full restore transcript, including the `[restore] ok` line and, for a
  point-in-time restore, the `[restore] point-in-time target=…` line
  (`infra/scripts/platform/pgbackrest-restore.sh`:189,702) and the
  `[restore] recovery state verified: pg_is_in_recovery()=false` line (`:596`).
- `restore-drill-report.json` and `transcript.txt` from the drill
  (`infra/scripts/platform/restore-drill.sh`:9-10), with `rto_pass`,
  `rpo_pass` and the fixture row count.
- The post-restore `/ready` bodies and the replay assertions above.
