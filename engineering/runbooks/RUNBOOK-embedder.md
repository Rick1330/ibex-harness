# Runbook: Embedder down / degraded (P1/P2)

**Scope.** The embedder (`services/embedder`) turns text into vectors for memory
write and search. It is a fail-closed readiness service: `/ready` returns 503
until its backend is wired and geometrically verified. Memory writes and vector
search degrade without it; the proxy's chat path does not.

## Symptoms

- Memory writes that embed before commit slow down or return 503.
- Worker embedding tasks back up (see the Worker Backlog runbook).
- Vector search returns nothing or stale results while full-text search still works.
- `GET /ready` on the embedder returns 503 with `code: service_not_ready`.

## Detection

1. Liveness vs readiness. `/health` is a static 200
   (`services/embedder/app/api/probes.py`:20-22). `/ready` is the real signal
   (`probes.py`:25-42):
   - 503 `{"error":{"code":"service_not_ready","message":...}}` when the backend
     is not wired or its startup verification failed.
   - 200 carries `profile`, `model_id`, `dimensions`, `backend`.
2. Startup geometry is fail-closed. The process refuses to become ready when TEI
   reports a different `model_id` than configured, or a vector dimension that
   does not match (`services/embedder/app/main.py`:79-104). The log line names
   both values: `TEI model mismatch: running model_id=... but configured model_id=...`.
3. Scrape the metrics endpoint. `/metrics` requires the bearer
   `IBEX_EMBEDDING_API_TOKEN` (`services/embedder/app/main.py`:280-284); Prometheus
   reads it from `/etc/prometheus/scrape-auth/embedder_metrics_bearer`
   (`infra/monitoring/prometheus/prometheus.yml`:35-43).

## First response

1. Read `/ready` and the last 200 log lines; do not restart before you know
   which check failed.
2. If the message names a model or dimension mismatch, **do not** force ready.
   The backend is serving different weights than the deployment records. Fix the
   configuration, not the probe.
3. If the backend is simply unavailable (TEI process down, hosted provider 5xx),
   restore or restart that dependency, then **restart the embedder** and re-poll
   `/ready`. The startup probe runs once, in the process lifespan
   (`services/embedder/app/main.py`:159-191, 212-244); restoring TEI alone does
   not re-run the geometry check or flip `/ready` to 200, because `state.ready`
   stays false until the process starts again.

## Recovery

1. **Model/revision mismatch.** Align the deployment with
   `engineering/MODEL_INVENTORY.md`:
   - `IBEX_EMBEDDING_MODEL` must match the backend's served `model_id`.
   - `IBEX_EMBEDDING_MODEL_REVISION` must match the pinned weights revision
     (`services/embedder/app/config.py`:43-52). Configuring it changes every
     cache digest, so old entries become misses and recompute.
   - If the revision is left unset, purge `{org_id}:embed:v1:*` for every
     organization before the first write against the new weights; otherwise the
     cache serves vectors from different weights as if they were current.
2. **TEI process down.** Start or restart TEI, then **restart the embedder** and
   poll `/ready` until 200. The startup geometry check runs once at process start
   (`services/embedder/app/main.py`:159-191, 212-244); restoring TEI does not
   re-run it, so `/ready` stays 503 until the embedder restarts and re-probes.
   `/health` returning 200 does not mean the model has loaded.
3. **Hosted backend 5xx.** Treat as a provider outage; the embedder reports
   503. Do not switch profiles to a stub to clear the probe: a stub writes
   schema-valid vectors of arbitrary geometry and silently corrupts recall.

## Escalation

- Escalate to the platform owner if the mismatch is in a released image (a model
  pin that disagrees with the inventory) rather than in deployment config.
- Escalate to security if the mismatch suggests a supply-chain change (served
  weights differ from the recorded revision with no deploy).

## Evidence to keep

- The exact `/ready` body and timestamp.
- The startup log line naming `model_id`/`dimensions`/`backend`.
- The `MODEL_INVENTORY.md` revision the deployment was pinned to.
- Whether any cache purge was run, and for which org keyspaces.
