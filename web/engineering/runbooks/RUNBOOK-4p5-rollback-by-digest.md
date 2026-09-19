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
     --set images.proxy="ghcr.io/.../proxy@sha256:<known-good>" \
     --set images.api="ghcr.io/.../api@sha256:<known-good>" \
     --set deployDigest="sha256:<known-good>"
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

## Automatic abort

Chart `rollout.maxUnavailable=0` and readiness probes abort progress when
pods stay unready past `progressDeadlineSeconds` (Kubernetes marks the
Deployment progress as failed). Operators then pin digests as above.
