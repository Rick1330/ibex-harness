# Runbook: Rollback by digest (Milestone 4.P.5)

## Trigger

- Canary/rolling update fails readiness (`/ready` critical deps) within `progressDeadlineSeconds`
- Kyverno `ibex-verify-images` rejects unsigned/wrong-digest Pods
- Restore drill or backup freshness alerts fire and require known-good code

## Procedure

1. Identify last known-good digests from CI (`docker-publish` job outputs /
   commit comment: `AUTH_DIGEST`, `PROXY_DIGEST`, `API_DIGEST`, …) or from
   `evidence_runs.deploy_image_digest`.
2. Update Helm values (do **not** use floating tags):

   ```bash
   helm upgrade ibex infra/helm/ibex-harness \
     -n ibex \
     -f infra/helm/ibex-harness/values-staging.yaml \
     --set-string images.proxy="ghcr.io/<org>/ibex-harness/proxy@sha256:<known-good>" \
     --set-string images.api="ghcr.io/<org>/ibex-harness/api@sha256:<known-good>"
     # (repeat for auth/worker/memory/embedder/mcpMemory as needed)
   ```

3. Confirm rollout:

   ```bash
   kubectl -n ibex rollout status deploy/proxy deploy/api --timeout=10m
   kubectl -n ibex get pods -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
   ```

4. **Never** roll back a Postgres migration without its compatibility procedure
   (`infra/scripts/db-migrate.sh down` only when the down migration is tested
   and the release notes allow it). Prefer forward-fix + digest pin of app images.

5. Attach rollback transcript + digests to the incident / evidence bundle.

## Failure detection (not automatic rollback)

Chart `rollout.maxUnavailable=0` and readiness probes can leave a Deployment
stuck when pods stay unready past `progressDeadlineSeconds`. Kubernetes then
records `ProgressDeadlineExceeded` on the Deployment condition — it does **not**
abort or roll back the Deployment by itself. Operators must follow the digest
pin procedure above (or rely on separate deployment automation that watches
that condition and rolls back).

## Backup schedule (operator / external)

`infra/scripts/platform/pgbackrest-backup.sh` is **not** scheduled by an in-chart
CronJob in 4.P.5. Operators must wire an external scheduler (platform CronJob,
systemd timer, or cloud scheduler) that:

1. Runs `pgbackrest-backup.sh full` (and incremental/WAL archive per site policy).
2. Exposes `ibex_postgres_last_backup_unixtime` for
   `infra/monitoring/prometheus/rules/ibex-platform-backup.yml`.

Placeholder digests (`sha256:000…`) in `values.yaml` are local stubs only.
Before staging/prod deploy, override every image with publish digests
(`helm upgrade … --set-string images.*@sha256:…` or CI-filled values). Guard:
`infra/scripts/platform/check-helm-digest-placeholders.sh` fails if
`values-staging.yaml` / `values-prod.yaml` still contain `sha256:000…`.
