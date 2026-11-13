# Runbook: MinIO / S3 object store down (P2)

**Scope.** The object store holds capture archives (buckets `ibex-sessions` and
`ibex-exports`) and backs the pgBackRest repository used by `make v1-backup`.
It is an S3-compatible endpoint (`S3_ENDPOINT`), envelope-encrypted with
`S3_MASTER_KEY_B64` for archived blobs.

**Profile reality.** MinIO runs in `infra/compose/dev/docker-compose.yml`:62-90
and the host dev overlay only. The supported `v1-single-node` Compose profile
does **not** define a MinIO service (`infra/compose/v1-single-node/compose.yml`
has no `minio` entry), so on that profile `S3_ENDPOINT` is whatever the operator
supplies. Do not assume a bundled MinIO exists where it is not defined.

## Symptoms

- Capture/redaction archives are missing for new sessions.
- Org deletion cannot purge object-store copies and stays incomplete.
- `make v1-backup` / pgBackRest fails against its S3 repository.
- Worker capture tasks log `S3_ENDPOINT unset` / `MASTER_KEY` / transport errors.

## Detection

1. Liveness of the dev MinIO: `curl -fsS http://127.0.0.1:9100/minio/health/live`
   (the container healthcheck probes the same path,
   `infra/compose/dev/docker-compose.yml`:78-85).
2. Bucket existence: `ibex-sessions` and `ibex-exports` are the configured
   targets (`services/worker/app/objectstore_client.py`:29;
   `infra/compose/dev/.env.example`:39-40). A reachable endpoint with a missing
   bucket fails the same upload.
3. pgBackRest: `pgbackrest --config=<conf> --stanza=ibex-main info` (the backup
   script runs this after every backup,
   `infra/scripts/platform/pgbackrest-backup.sh`:38-39). A failed `repo1-s3`
   connect means the backup is not running.
4. Worker capture behaviour. **Redaction captures** handled by `_persist_redacted`
   swallow a missing `S3_ENDPOINT` or master key: the `RuntimeError` is caught and
   the upload skipped (`services/worker/app/tasks/capture_redaction.py`:208-213).
   **Full-archive captures** handled by `_archive_payload` do **not** catch it, so
   the same error propagates and fails the task (`:223-233`). Absence of a
   redaction archive is not proof the store is healthy.

## First response

1. Confirm the endpoint is reachable and the bucket exists; restart the store
   only after that check.
2. If the failure is credential-related (access/secret key), fix the operator
   configuration; do not rotate the envelope master key to clear an auth error.
3. If pgBackRest cannot reach the store, the backup did not run. Treat the last
   successful backup as the recovery point and escalate; do not start a restore
   against a repository you cannot read.

## Recovery

- **Dev MinIO down:** `docker compose -f infra/compose/dev/docker-compose.yml up -d minio`
  (it depends on `minio-init` for bucket creation,
  `docker-compose.yml`:53,75-77), then re-check the health path and buckets.
- **Missing bucket:** recreate `ibex-sessions` / `ibex-exports` and re-run the
  failed capture or backup.
- **Encrypted blob cannot be read:** this is a master-key problem, not an object
  store problem, and the key is the **archive** key — `S3_MASTER_KEY_B64` (or its
  alias `OBJECTSTORE_MASTER_KEY_B64`), read in
  `services/worker/app/objectstore_client.py`:137-143. That is **not**
  `IBEX_CREDENTIALS_MASTER_KEY`, which decrypts provider credentials (see the
  restore and master-key runbooks). Point recovery at the archive key; the
  archive is unrecoverable without the key that sealed it.
- **Org-deletion purge incomplete:** after the store recovers, re-run the
  deletion job targeting the recorded object URIs; do not mark the org deleted
  while copies remain.

## Escalation

- Escalate to infrastructure when the S3 endpoint or its credentials are the
  owner's, and to security when archives appear under an unexpected bucket or
  prefix.
- Escalate to the owner if `v1-single-node` is being expected to provide object
  storage it does not define.

## Evidence to keep

- Health-probe output and bucket listing.
- The exact `pgbackrest info` output before and after recovery.
- The object URIs the deletion/capture job reported, with the org id.
- Whether an archive was skipped silently versus failed loudly.
