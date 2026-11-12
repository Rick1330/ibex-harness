# Failure Modes and Readiness

**Status:** `specified` target failure contract.

| Dependency | Class | Failure behavior |
|---|---|---|
| Auth/principal/policy | Authority | Deny or typed 503; no provider/tool work. |
| Budget/reservation | Authority/integrity | Deny or 503; no hard-budget claim. |
| Redis on protected path | Integrity/coordination | 503 under configured production profile; no permissive local fallback. |
| Context/memory quality | Quality | Directive-only or verified hot-cache context; never wider visibility. |
| Embedder/reranker/model | Quality/async | Queue, fallback, quarantine, or abstain. |
| Provider | External | Typed error, bounded retry/breaker/fallback. |
| Evidence outbox | Integrity | Durable buffer or uncertified response; never silent loss. |
| ClickHouse/OTel | Projection | Buffer or degraded analytics; canonical evidence remains. |
| Object storage | Artifact | Block artifact-dependent action or use verified retained reference. |
| Queue/worker | Async | Retry/DLQ/replay with operation status. |

`/health` is liveness. `/ready` means the selected profile’s required dependencies and contracts are available; optional quality services may be degraded and visibly reported. Readiness must not report healthy when security or evidence integrity is unavailable.

Graceful shutdown drains streams, stops new admissions, cancels bounded work, persists worker state, and reports completion. No process assumes a retry is safe unless the operation is idempotent.

## Alert rules and the failure modes they enforce

Every rule under `infra/monitoring/prometheus/rules/` maps to a row above, or states explicitly that it covers
availability or recoverability rather than a dependency. The route column is the destination defined in
[`infra/monitoring/alertmanager/alertmanager.yml`](../../infra/monitoring/alertmanager/alertmanager.yml); the severity
vocabulary, the legacy aliases and the per-environment webhook are documented in
[`alertmanager/README.md`](../../infra/monitoring/alertmanager/README.md).

Rule count: 14 production rules, reviewed by hand against the table below. The count is not what the gate
checks: `python3 infra/scripts/check-alert-routing.py` proves that every rule severity reaches a real
receiver, that no receiver is a null/discard, and that no rule carries an unlabelled severity — it does
not count rules, so a rule added with a routed severity passes it. The two synthetic probes under
`rules/test/` are listed separately: they never load in the default stack.

| Alert | Failure mode (from this doc) | Severity | Route | Owner action |
|---|---|---|---|---|
| `IbexProxyDown` | Availability, not a dependency row: the front door is gone, so every dependency row is unreachable. | `p1` (→ page) | `ibex-page` → `/alerts/page` | Check proxy process and `/ready`; restart; confirm ingress. |
| `IbexAuthDown` | Auth/principal/policy | `p1` (→ page) | `ibex-page` → `/alerts/page` | Restore auth issuance/validation; verify `/ready` and token validation. |
| `IbexProxyHighErrorRatio` | Provider, with Auth/principal/policy as the second cause | `p1` (→ page) | `ibex-page` → `/alerts/page` | Split 5xx by cause; check provider latency/breaker state; confirm no auth denial storm. |
| `IbexProcessNotUp` | Availability, not a dependency row: a scraped process is not running (covers every service). | `p1` (→ page) | `ibex-page` → `/alerts/page` | Identify the `service` label; check the process log and its restart policy. |
| `IbexMemoryDown` | Context/memory quality (degrades to directive-only context) | `p2` (→ ticket) | `ibex-digest` → `/alerts/digest` | Confirm the proxy is degrading to directive-only context rather than failing; restart memory. |
| `IbexMemoryAfterCommitFailures` | Redis on protected path, surfacing as Context/memory quality divergence | `p2` (→ ticket) | `ibex-digest` → `/alerts/digest` | Reconcile Postgres rows against Redis object cache and the vector index; check write-cache errors. |
| `IbexMCPAuditDrops` | Evidence outbox (audit events must not be silently lost) | `p2` (→ ticket) | `ibex-digest` → `/alerts/digest` | Check the audit queue consumer; quantify dropped events before trusting the audit trail. |
| `IbexMemoryEscalationBacklogGrowth` | Queue/worker, with no consumer shipped yet | `p3` (→ ticket) | `ibex-digest` → `/alerts/digest` | Review `memory_conflict_escalations` growth and the retention policy; escalate if it is transactional. |
| `IBEXPostgresBackupStale` | Durability/RPO, not a dependency row: the backup is the recoverability evidence. | `page` | `ibex-page` → `/alerts/page` | Run `infra/scripts/platform/pgbackrest-backup.sh`; check the MinIO repo; RPO budget is ≤5m. |
| `IBEXWorkerTaskDeadLettered` | Queue/worker | `page` | `ibex-page` → `/alerts/page` | Inspect `ibex_core.failed_tasks` for the `task_name`; fix the cause, then replay. |
| `IBEXRestoreDrillMissing` | Recoverability, not a dependency row: the drill proves the backup is usable. | `ticket` | `ibex-digest` → `/alerts/digest` | Run `infra/scripts/platform/restore-drill.sh`; make its evidence scrapeable. |
| `IbexProxyOverheadFastBurn` | Latency budget, not a dependency row: the proxy's own enforcement overhead is exceeding the ratified p99 ≤20 ms objective fast enough to spend ~2% of the error budget per hour. The dependency rows it can implicate are Redis on protected path and Auth/principal/policy. | `page` | `ibex-page` → `/alerts/page` | Run `engineering/runbooks/RUNBOOKS.md` §2; compare `ibex:sli_proxy_overhead:burn_rate_1h` with the auth-cache, rate-limit and directive-cache panels; roll back the recent proxy deploy when correlated. |
| `IbexProxyOverheadSlowBurn` | Latency budget, not a dependency row: same objective, burning ~5% of the budget per six hours with no single bad window — a drift that exhausts the budget in days. | `ticket` | `ibex-digest` → `/alerts/digest` | Same runbook, no page: confirm the 6h window, bisect by deploy, and check for an allocation-heavy change on the hot path. |
| `IbexProxyOverheadSLIAbsent` | Observability, not a dependency row: the SLI itself is missing or present but not advancing on the `assembly="disabled"` population, so both burn alerts are inert and silence is indistinguishable from health. | `ticket` | `ibex-digest` → `/alerts/digest` | Check `up{job="proxy"}`; confirm `ibex_proxy_nonstreaming_requests_total{assembly="disabled"}` advances while `ibex_proxy_overhead_seconds_count{assembly="disabled"}` does not; check the build exports `ibex_proxy_overhead_seconds` and that `0.02` is still the rendered 20 ms bucket label. |

Test-only probes (loaded only by `infra/compose/observability/docker-compose.alerting-test.yml`):

| Alert | Failure mode | Severity | Route | Owner action |
|---|---|---|---|---|
| `IbexAlertDeliveryProbePage` | Not a failure: proves the `page` channel is wired to a real receiver. | `page` | `ibex-page` → `/alerts/page` | None. Fires only during `make alert-delivery-test`. |
| `IbexAlertDeliveryProbeTicket` | Not a failure: proves the `ticket` channel is wired to a real receiver. | `ticket` | `ibex-digest` → `/alerts/digest` | None. Fires only during `make alert-delivery-test`. |
| `IbexSloBurnProbe` | Not a failure: a constant 50× burn rate that proves an SLO burn alert can fire and route with no proxy traffic. It makes no claim about the real SLI — that is what `rules/test/unit/ibex-slo-burn.test.yml` asserts. | `page` | `ibex-page` → `/alerts/page` | None. Fires only in the alerting-test stack. |
