# World-Class Cross-Cutting Audit: `ibex-harness` Before Track D

**Repository:** `Rick1330/ibex-harness`  
**Branch:** `main`  
**Audited revision:** `5d7e0f21af402b551351e6272da7f5464e106d1b`  
**Freshness:** The repository was fetched and hard-reset to `origin/main` before inspection.  
**Scope:** New findings across 13 engineering angles. The prior trace-inspector findings are treated as known and are not repeated except where new evidence changes their severity or scope.

## Executive summary

The live repository contains several issues that should be resolved or explicitly risk-accepted before Track D is treated as production-ready. The most severe are authorization fail-open behavior and cross-store deletion inconsistency. When Postgres is unavailable, the proxy can construct a passthrough model-policy registry that allows every model for every organization. Separately, organization deletion can report success after cleaning only Postgres, while ClickHouse and MinIO data remain. Model-policy invalidation also uses a lossy Postgres-to-Redis Pub/Sub dual write, allowing stale authorization decisions. These are P0/P1 risks because they affect tenant controls, erasure, and authorization semantics.

The principal reliability risks are equally broad. API readiness is startup-only, streaming writes have no finite downstream deadline, post-response queues can block request goroutines, and maintenance tasks lack execution limits. Context budgeting omits serialized/tool overhead, memory embeddings lose model identity, and tenant-filtered ANN search has no safe iterative-scan default. Track D also lacks production deployment manifests, full backup/restore evidence, protected Python and Semgrep gates, and a complete externalized contract-testing strategy.

## Severity and classification

- **P0:** Tenant-isolation or security break.
- **P1:** Production correctness, availability, or security defect.
- **P2:** Hardening, scalability, privacy, or release-process gap.
- **P3:** Documentation/process drift only.

Classifications are **undocumented-but-real bug**, **documented-but-unimplemented**, **implemented-but-unreachable-by-consumer**, or **docs-stale**. External sources are labeled by type and confidence.

## 1. AuthN/AuthZ, multi-tenancy, and data isolation

### 1.1 Revocation invalidation is best-effort

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/auth/internal/service/token_service.go:146-187` marks tokens revoked in the database, then publishes invalidation asynchronously and treats publication failure as non-fatal. `packages/revocation/publisher.go:71-75` defines a silent `NoopPublisher`; `packages/authcache/validator.go:138-156,205-241` serves LRU hits until local TTL or token expiry; `services/proxy/internal/config/config.go:304-315` makes the stale window deployment-configurable.

A proxy can accept a revoked bearer after the database has recorded revocation. Make invalidation fail closed or use a durable/versioned revocation source, remove silent production no-op behavior, and test Redis loss during emergency revocation.

**External authority:** OWASP API Security Top 10 API2, [Broken Authentication](https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/) — **official standard; high confidence**. OWASP’s control objective requires continued validation of token validity; a stale authorization cache violates that objective.

### 1.2 RLS service-account bypass relies on a mutable application GUC

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up; normal HTTP reachability is not shown.

`infra/migrations/postgres/000004_rls.up.sql:1-37` and later tenant migrations, including `000024_organization_invites.up.sql:27-39` and `000027_provider_credentials.up.sql:36-48`, grant unrestricted access when `current_setting('app.is_service_account', true) = 'true'`. `services/api/app/db.py:19-23`, `packages/session/rls.go:20-26`, and `services/worker/app/db.py:37-47` set that context from application code rather than database-attested identity.

A compromised SQL-capable path or permissive role could bypass forced RLS across tenants. Use a dedicated non-login service role or security-definer capability, revoke untrusted `SET`/role escalation, and test that request roles cannot set the bypass.

**External authority:** [PostgreSQL Row Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — **official standard; high confidence**. PostgreSQL identifies role ownership and `BYPASSRLS` as security boundaries. [AWS pooled-tenant RLS guidance](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/) — **vendor engineering blog; medium confidence** — recommends database-enforced tenant identity rather than application convention alone.

## 2. Proxy hot path and networking

### 2.1 SSE forwarding permits a non-reading client to pin resources

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/proxy/internal/http/stream_forward.go:52-66,83-86` clears the write deadline to `time.Time{}`. `:158-197` synchronously writes each SSE line, and `packages/provider/httputil.go:64-80,96-104` keeps the upstream response open until forwarding returns.

A connected client that stops reading can block `ResponseWriter.Write`, consuming a handler, socket, upstream connection, and provider capacity. Keep a finite or idle-progress write deadline, cancel both bodies on expiry, and add slow-consumer integration tests.

**External authority:** [Go `net/http.ResponseController`](https://pkg.go.dev/net/http#ResponseController) — **official documentation; high confidence**. A zero write deadline means no deadline, so the current code creates an unbounded downstream wait.

### 2.2 Post-response checkpoint queue backpressure blocks request goroutines

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/proxy/internal/asyncpool/pool.go:48-61` blocks on `p.jobs <- fn` with no context, timeout, or queue-full result. `services/proxy/internal/http/chat_session_bridge.go:99-115` and `chat_provider.go:229-247,313-339` enqueue from request paths. Defaults are eight workers and a 256-item queue (`services/proxy/internal/config/config.go:45-47`).

When checkpoint work falls behind, completed requests wait behind the full queue, amplifying downstream failure into goroutine and latency exhaustion. Make enqueue deadline-aware/non-blocking, shed post-response work explicitly, and make shutdown cancellation-safe.

**External authority:** [Google SRE, Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/) — **vendor engineering guidance; high confidence**. Bounded queues must be paired with load shedding; otherwise waiting callers become an unbounded secondary queue.

### 2.3 Provider active connections are unbounded

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Low. **Track D:** Follow-up.

`packages/provider/httputil.go:49-60` sets `MaxIdleConns=100` and `MaxIdleConnsPerHost=20`, but not `MaxConnsPerHost`. The transport is shared by synchronous and streaming clients (`:21-24,64-68`).

Active and dialing connections can grow without an explicit cap during bursts or slow streams. Set `MaxConnsPerHost`, expose dial/active counts, and combine the cap with admission control.

**External authority:** [Go transport source](https://go.dev/src/net/http/transport.go) — **official documentation; high confidence**. `MaxConnsPerHost` limits dialing, active, and idle connections; zero means unlimited.

### 2.4 Public trace context and request IDs can amplify telemetry and spoof correlation

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`packages/telemetry/spanmiddleware.go:18-23` accepts inbound propagation headers before creating server spans; `packages/telemetry/sampler.go:7-11` uses `ParentBased(TraceIDRatioBased(ratio))`. Separately, `services/proxy/internal/http/middleware.go:19-30,63-75` and `packages/reqid/reqid.go:33-43` preserve a valid client UUID as the internal request ID and propagate it through gRPC (`reqid.go:20-21`).

Untrusted callers can force sampled-parent behavior and choose the internal correlation identity. Generate proxy-owned internal IDs, retain client correlation separately, sanitize trace context at the public boundary, and bound trace headers.

**External authority:** [W3C Trace Context security](https://www.w3.org/TR/trace-context/) — **official standard; high confidence**. [Envoy tracing documentation](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/observability/tracing) — **vendor documentation; high confidence** — distinguishes trusted internal IDs from client correlation IDs.

## 3. gRPC/proto contracts and service boundaries

### 3.1 Auth outcomes depend on free-form status text

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** Follow-up.

`services/auth/internal/grpc/server.go:120-131,365-384` emits literal `PermissionDenied` messages. `services/proxy/internal/auth/validator.go:43-54` requires exact text for organization suspension, while `agent_verifier.go:112-126` uses substring matching for inactive agents.

A harmless wording change can change a suspension into auth-unavailable or authorization failure. Define stable protobuf error details/reason values and map consumers by status plus structured reason.

**External authority:** [gRPC status codes](https://grpc.io/docs/guides/status-codes/) and [richer error model](https://grpc.io/docs/guides/error/) — **official standards; high confidence**. Error messages are descriptive text, not a stable machine contract.

### 3.2 Caller cancellation is returned as `DEADLINE_EXCEEDED`

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/context/app/server.py:86-90,107-115` converts `CancelledError` and `context.cancelled()` to `DEADLINE_EXCEEDED`; ADR-0071 documents the conflation at `web/content/docs/adr/0071-context-grpc-degradation-deadline.mdx:33-44`.

Consumers cannot distinguish caller abort from deadline expiry, so retry, alerting, and fail-open logic can be wrong. Preserve `CANCELLED` for caller cancellation and test both cases across Python and Go.

**External authority:** [gRPC status codes](https://grpc.io/docs/guides/status-codes/) — **official standard; high confidence**. `CANCELLED` and `DEADLINE_EXCEEDED` have distinct defined meanings.

### 3.3 Proto breaking checks and generated contracts are not fully enforced

**Severity:** P2. **Classification:** Documented-but-unimplemented. **Difficulty:** Low–Medium. **Track D:** Follow-up.

`.github/workflows/ci.yml:283-309` allows `buf-breaking` to fail with `continue-on-error: true`. `packages/proto/buf.yaml:7-9` selects FILE checks, but branch protection does not require the job. Remote plugins are unpinned in `packages/proto/buf.gen.yaml:6-16`, generated output is ignored by `packages/proto/.gitignore:1`, and Python runtime dependencies are lower-bound-only (`services/context/pyproject.toml:17-18`).

Breaking changes can merge and regeneration can vary by environment. Make compatibility checks required, pin plugins/runtime versions, and verify generated outputs in CI.

**External authority:** [Buf breaking checks](https://buf.build/docs/breaking/) and [remote plugin usage](https://buf.build/docs/bsr/remote-plugins/usage/) — **vendor documentation; high confidence**.

### 3.4 Contract tests do not exercise all real service consumers

**Severity:** P2. **Classification:** Implemented-but-unreachable-by-consumer. **Difficulty:** Medium. **Track D:** Follow-up.

`packages/proto/proto/ibex/auth/v1/auth.proto:11-39` declares nine RPCs, but `packages/proto/auth_grpc_contract_test.go:14-75` exercises only five. Embedded unimplemented servers mask omissions. `context_contract_test.go:56-103` uses a no-op Context server, and CI runs only these proto tests (`.github/workflows/ci.yml:339-356`).

The suite proves generated wiring, not concrete Go-to-Python compatibility. Add consumer-driven tests for every RPC and run the real service implementations in required CI.

**External authority:** [Pact](https://docs.pact.io/) — **vendor documentation; high confidence**. Contract tests must exercise concrete consumer/provider interactions, not only descriptors or no-op registrations.

## 4. Multi-provider/model routing and resilience

### 4.1 No fallback route exists for a degraded selected provider

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** High. **Track D:** Follow-up.

`packages/provider/registry.go:18-32,70-80` retains one provider per model. `provider_routing_middleware.go:62-80` selects one provider, and `chat_provider.go:83-102` calls it once and returns failure.

A transient or model-specific outage becomes a client-visible failure even when another compatible route exists. Define tenant-aware ordered fallback with a bounded total deadline and streaming/idempotency rules.

**External authority:** [Azure Retry pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry) — **vendor guidance; high confidence**. Resilient systems should invoke an alternative service or degraded path when the original fault is not transiently recoverable.

### 4.2 Circuit-breaker state is shared across all models behind a provider

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/proxy/internal/bootstrap/provider.go:225-270` creates one breaker per provider and passes it to clients serving multiple models. `packages/provider/breaker_wrap.go:25-62` accounts all requests under that shared breaker.

One failing model can open the breaker for healthy siblings. Key state by provider/model/endpoint, while retaining a separate shared-transport breaker where appropriate.

**External authority:** [Azure Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker) — **vendor guidance; medium confidence**. Breaker state should represent a coherent failing operation/failure domain.

### 4.3 Static model catalog accepts lifecycle-stale models

**Severity:** P1. **Classification:** Docs-stale. **Difficulty:** Medium. **Track D:** Follow-up.

`packages/provider/capability_catalog.go:5-49` is hand-coded and `services/proxy/internal/bootstrap/provider.go:190-198` builds the registry only at startup. `packages/provider/openai/client.go:51-60` accepts `gpt-4-turbo`, while the provider has a documented shutdown schedule.

Add freshness, deprecation, replacement IDs, and controlled refresh/review rather than discovering retirement only at request time.

**External authority:** [OpenAI deprecations](https://platform.openai.com/docs/deprecations) — **official provider documentation; high confidence**. Provider model lifecycle changes require application updates.

### 4.4 Capability registry advertises Anthropic tool support that the adapter rejects

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** High. **Track D:** Follow-up.

`packages/provider/capability_catalog.go:12-13,32-34` marks Claude rows `SupportsTools=true`, but `packages/provider/anthropic/request.go:147-163` rejects tool-role messages. The normalized request model lacks a complete tool declaration/result path (`packages/provider/provider.go:19-36`).

Either implement translation or publish adapter-effective `SupportsTools=false`, with capability-derived acceptance tests.

**External authority:** [Anthropic Models overview](https://docs.anthropic.com/en/docs/about-claude/models/overview) — **official provider documentation; high confidence**. Vendor support does not imply adapter support; the registry must describe the effective consumer contract.

## 5. Tokenizer, context assembly, and memory correctness

### 5.1 Estimated budgets omit provider and formatter overhead

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** Follow-up; blocks near-window tool-enabled flows.

`services/context/app/estimate.py:1-38` uses character/rune approximations; `budget.py:55-85` omits formatter overhead; `formatter.py:173-247` adds safety prose, wrappers, escaping, and tools; `assemble.py:134-142,178-188` packs and reports from the estimate.

Count the exact provider payload or a proven upper bound, including roles, boundaries, tools, wrappers, and output reserve.

**External authority:** [OpenAI token counting](https://developers.openai.com/api/docs/guides/token-counting) and [Anthropic context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows) — **official provider documentation; high confidence**.

### 5.2 Declared budget/version controls are unreachable from the proxy

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** Follow-up.

The proto declares `session_id`, `directive_version_id`, `available_tokens`, and scoring fields (`packages/proto/proto/ibex/context/v1/context.proto:21-41`), but `packages/contextclient/types.go:16-26`, `map.go:7-24`, `chat_context_assemble.go:119-130`, and `services/context/app/server.py:349-374` omit or ignore them.

Thread supported fields through the live path, define precedence against catalog limits, and test that changed values alter packing.

### 5.3 Embedding model identity is discarded and vectors are mixed

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** High. **Track D:** Follow-up.

`services/memory/app/clients/embedding.py:85-90,286-298` receives `model_id`; `pipeline/stages.py:110-120` drops it; `write/orchestrator.py:221-234` hard-codes `bge-m3`. `vectorstore/pgvector_store.py:15-69` searches without model/version filtering, and migration `000017_memory_schema_v2_expand.up.sql:12-37` checks dimensions but not profile identity.

Persist immutable embedding profile/version, filter queries by profile, and use blue/green or named-vector re-embedding for model changes.

**External authority:** [Qdrant embedding-model migration](https://qdrant.tech/documentation/tutorials-operations/embedding-model-migration/) — **official vendor documentation; high confidence**. Old and new embedding spaces require parallel migration rather than silent mixing.

### 5.4 Post-commit cache refresh can regress concurrent scores

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`feedback/persist.py:19-67` serializes the database update, but `feedback/service.py:19-23` refreshes Redis afterward. `write/cache.py:54-72,87-101` writes the snapshot without version/CAS.

Refresh order B then A can leave Redis older than Postgres. Use row versions with Redis CAS/Lua or an ordered outbox consumer.

**External authority:** [Redis transactions](https://redis.io/docs/latest/develop/using-commands/transactions/) — **official documentation; high confidence**. Concurrent read/modify/write requires optimistic locking or equivalent version checks.

### 5.5 `max_memories` truncates retrieval order before scoring

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Low. **Track D:** Follow-up.

`services/context/app/assemble.py:227-230` applies `scored[:options.max_memories]` while scores still preserve input order (`scoring.py:40-45`). Canonical sorting occurs only later in `packer.py:152-159,243-259`.

Merge/deduplicate, score, rerank, then apply the cap. Add a test where a high-score candidate appears after the prefix.

**External authority:** [Pinecone reranking](https://docs.pinecone.io/guides/search/rerank-results) — **official vendor documentation; high confidence**. Candidate retrieval must precede reranking and final top-N selection.

## 6. Observability, operational hardening, and incident readiness

### 6.1 Redis subscriber reconnects lack jitter

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Low–Medium. **Track D:** Follow-up.

`packages/redissub/loop.go:74-80,112-147` uses deterministic 1s-to-30s backoff without randomization for revocation/directive subscribers.

Fleet-wide reconnect waves can overload Redis during recovery. Use full jitter, metrics, alerts, and deterministic tests.

**External authority:** [Google SRE, Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/) — **official SRE guidance; high confidence**.

### 6.2 Session identifiers are emitted into logs

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Low–Medium. **Track D:** Follow-up.

`services/proxy/internal/http/router.go:300-310` logs raw paths containing session IDs. `session_terminate.go:263-324` logs `external_id` and `session_id`, while `packages/logger/redact.go:8-25` does not sanitize these path/error values.

Use request/trace IDs or approved pseudonyms, sanitize paths and nested errors, and add centralized redaction tests.

**External authority:** [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — **official standard; high confidence**. Session identifiers should be masked, hashed, or omitted.

## 7. Data layer: consistency, migrations, backup/DR, retention, and scale

### 7.1 Committed memories can remain permanently unembedded

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** **Blocker for dependable memory retrieval**.

`services/memory/app/write/orchestrator.py:61-78` commits before `_run_after_commit`; `after_commit.py:24-55` catches failures without durable retry. Null embeddings are allowed by `000017_memory_schema_v2_expand.up.sql:12-25`, and `pgvector_store.py:15-30` excludes them.

Use same-transaction embedding or a durable transactional outbox/reconciliation worker.

**External authority:** [AWS Transactional Outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) — **official guidance; high confidence**.

### 7.2 Backup/restore and cross-store DR are not implemented or evidenced

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** High. **Track D:** **Blocker for credible production rollout/upgrade approval**.

Compose defines local volumes only (`infra/compose/dev/docker-compose.yml:11-64`); `infra/scripts/db-migrate.sh:25-33` has no backup/restore; deployment documentation requires verification without an executable workflow (`web/engineering/DEPLOYMENT.md:184-186`); backup bucket variables exist without uploader/consumer (`ENVIRONMENT_VARIABLES.md:190-199`).

Define RPO/RTO, implement encrypted off-host backup/PITR or equivalent for each store, and run isolated full-stack restore tests that verify cross-store references.

**External authority:** [Google SRE Data Integrity](https://sre.google/sre-book/data-integrity/) — **official SRE guidance; high confidence**. Backup value is established by tested recovery, not by storage configuration alone.

### 7.3 Migrations include live-write-unsafe operations

**Severity:** P2. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** Follow-up/release hardening.

`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:91-98` uses plain `CREATE INDEX`; `000020_memory_conflict_escalation_status_enum.up.sql:14-29` performs blocking type/index operations. These conflict with the expand/contract rules in `web/engineering/DEPLOYMENT.md:197-215,228-243`.

Use concurrent index builds, compatibility columns, validation phases, lock timeouts, and production-sized concurrent-write tests.

**External authority:** [PostgreSQL `CREATE INDEX`](https://www.postgresql.org/docs/current/sql-createindex.html) — **official standard; high confidence**.

### 7.4 Tenant-filtered ANN search lacks a safe iterative-scan default

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** **Blocker for predictable retrieval quality/latency at scale**.

`pgvector_store.py:15-30` applies tenant filters to a shared ANN query; migration `000017...:94-98` creates one shared HNSW index; `vectorstore/base.py:50-67` and `pgvector_store.py:96-102` make iterative scan opt-in.

Small tenants can receive too few or lower-recall results as the shared index grows. Enable/tune iterative scans or use partitioning/tenant-specific strategies, with per-tenant recall and p99 benchmarks.

**External authority:** [pgvector documentation](https://github.com/pgvector/pgvector) — **project/community documentation; high confidence**.

### 7.5 ClickHouse retention is hard-coded to 90 days

**Severity:** P2. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** Follow-up.

`infra/migrations/clickhouse/000001_create_llm_traces.up.sql:33-39` and `000002_create_mcp_tool_calls.up.sql:16-21` hard-code 90-day TTLs, while `web/engineering/SECURITY.md:424-428` promises configurable/compliance retention.

Represent retention by tenant/tier/data class, monitor expiry lag, and define legal-hold interaction.

**External authority:** [Google SRE Data Integrity](https://sre.google/sre-book/data-integrity/) — **official SRE guidance; high confidence**.

## 8. Distributed-systems correctness

### 8.1 Model-policy invalidation is a lossy database-to-Pub/Sub dual write

**Severity:** P0. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up, but a security-critical authorization defect.

`services/api/app/services/model_policies.py:184-276` commits the database then best-effort publishes. `model_policy_publish.py:47-63` uses Redis `PUBLISH`; `packages/modelpolicy/subscriber.go:66-105` has no replay; `cache.go:73-169` serves stale snapshots until TTL.

A proxy can retain an old allow/deny policy after mutation. Use a same-transaction versioned outbox, durable relay, version-aware consumers, reconciliation, and fail-closed behavior when policy version is unknown.

**External authority:** [Redis Pub/Sub](https://redis.io/docs/latest/develop/pubsub/) — **official documentation; high confidence** — Pub/Sub is at-most-once and disconnected subscribers lose messages. [Zanzibar paper](https://www.usenix.org/system/files/atc19-pang.pdf) — **peer-reviewed conference paper; high confidence** — identifies stale ACLs and update ordering as a core authorization problem.

### 8.2 Organization deletion has a broker/database commit race

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/api/app/services/organizations.py:271-280` dispatches before commit; `:215-235` uses a separate thread. `services/worker/app/tasks/org_deletion.py:73-75,112-132` skips invisible/non-pending jobs without reconciliation. `infra/migrations/postgres/000025_org_deletion_jobs.up.sql:2-14` has no outbox.

A worker can consume an accepted task before the row is visible and permanently skip deletion. Use a transactional outbox or commit-first durable dispatcher, and make temporary invisibility retryable.

**External authority:** [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html) — **established engineering pattern; high confidence**.

### 8.3 Idempotency is fail-open at Redis failure and releases keys after 5xx

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** High. **Track D:** Follow-up.

`services/proxy/internal/http/chat/idempotency.go:159-164` proceeds on Redis claim failure; `:244-267` releases claims for 429/5xx; `:315-327` logs commit failure. `packages/idempotency/redis.go:90-130` has no durable operation record.

An ambiguous provider operation can be invoked again with the same key. Use a durable ledger or fail closed, retain ambiguous state, reconcile upstream, and propagate stable request IDs.

**External authority:** [AWS idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) and [Stripe idempotency](https://docs.stripe.com/api/idempotent_requests) — **vendor/official API guidance; high confidence**.

## 9. Deployment, infrastructure, and supply chain

### 9.1 Production application deployment topology is absent

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** High. **Track D:** Follow-up before production rollout.

Deployment documentation says Helm/Kustomize and official service images/manifests do not exist (`web/content/docs/deployment/kubernetes.mdx:14-20,86-122`). `infra/README.md:18-40` lists only observability Helm and future application charts.

Add versioned application manifests with immutable digests, probes, limits, NetworkPolicy, PDBs, secret references, migration ordering, rollout checks, and smoke promotion gates.

**External authority:** [Kubernetes rolling updates](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/) — **official standard; high confidence**.

### 9.2 Worker image is outside vulnerability-scan and publish gates

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

Compose runs the worker (`infra/compose/dev/docker-compose.yml:72-96`), but `.github/workflows/docker-publish.yml:320-620,1062-1069,1101-1106,1143-1149` has no worker build, scan, or notification dependency.

Add worker build, scan, SBOM, provenance, digest reporting, and promotion dependency.

**External authority:** [NIST SSDF SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) — **official standard; high confidence**.

### 9.3 Repository SBOM is not image-bound or promotion-coupled

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`.github/workflows/sbom.yml:3-46` and `release.yml:79-86` run Syft on `path: .`; `docker-publish.yml:991-1057` attests image digests without depending on the SBOM workflow.

Generate and sign an SBOM for each exact image digest and make promotion depend on it.

**External authority:** [SLSA FAQ](https://slsa.dev/spec/v1.0/faq) — **official specification guidance; high confidence**.

### 9.4 Local secrets use weak defaults and lack rotation/reload

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

Compose defaults include `ibex/ibex`, `minioadmin/minioadmin`, and `dev-enqueue-token` (`infra/compose/dev/docker-compose.yml:4-8,53-91`; test credentials at `infra/compose/test/docker-compose.yml:3-8,56-63`). Kubernetes secret delivery is only preview/future work (`kubernetes.mdx:86-120`), with no rotation job in the audited inventory.

Remove usable defaults from runnable paths, require generated/untracked secrets, implement external-secret delivery, and test rotation/restart semantics.

**External authority:** [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) — **official standard; high confidence**.

### 9.5 Stateful migration rollback is destructive and ungated

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** High. **Track D:** Follow-up/release blocker.

`infra/scripts/db-migrate.sh:25-33` and Make targets expose `down` without environment guard. `000017_memory_schema_v2_expand.down.sql:1-54` drops data-bearing fields, while `000026_agent_default_provider_model.up.sql:3-4` creates `NOT VALID` constraints without a follow-up validation migration.

Make production migration forward-only, use expand/contract, require backup/restore preflight, and define rollback as traffic rollback plus forward repair rather than destructive down.

**External authority:** [Kubernetes StatefulSet guidance](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) — **official standard; high confidence**.

## 10. Scalability, capacity, and cost

### 10.1 Worker deletion tasks create unbudgeted SQLAlchemy pools

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/worker/app/db.py:20-29` creates an engine with default pool limits per task; `org_deletion.py:65-72,107-109` creates/disposes it per invocation. Worker concurrency/prefetch are four/four (`config.py:116-118`, `celery_app.py:60-72`).

Aggregate connections can exhaust Postgres. Use one process-scoped engine with explicit pool sizing and aggregate capacity tests.

**External authority:** [SQLAlchemy pooling](https://docs.sqlalchemy.org/en/latest/core/pooling.html) — **official documentation; high confidence**.

### 10.2 Revocation tombstones bypass the auth-cache LRU bound

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

The LRU is bounded by `packages/authcache/config.go:8-39`, but `token_index.go:11-16,72-95` stores tombstones in an unbounded map and prunes only when the same token is revisited.

High-cardinality revocations can grow process memory despite bounded LRU telemetry. Use bounded expiring tombstones and pruning metrics.

**External authority:** [Redis eviction guidance](https://redis.io/docs/latest/develop/reference/eviction/) — **vendor documentation; high confidence**.

### 10.3 Load benchmarks do not establish breakpoints or failure behavior

**Severity:** P2. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** Follow-up.

`benchmarks/k6/proxy_load.js:9-60` tests health or one ping request; `.github/workflows/benchmark.yml:187-202,254-270` limits runs to short 15-second, 30-second, or two-minute profiles without fault injection.

Add open-loop staged stress, realistic multi-tenant mixes, dependency faults, soak tests, and breakpoint/safety-margin gates.

**External authority:** [Google SRE Testing for Reliability](https://sre.google/sre-book/testing-reliability/) — **official SRE guidance; high confidence**.

### 10.4 Tenant model governance has no cumulative usage/spend control

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** High. **Track D:** Follow-up.

`infra/migrations/postgres/000029_org_model_policies.up.sql:4-20` and `packages/modelpolicy/store.go:88-110` store allow/deny policy only. `services/proxy/internal/validation/chat.go:108-121` and `limits.go:11` enforce per-request limits, not period budgets.

Add atomic period budgets, reservations, actual-use reconciliation, hard caps, and concurrent quota tests.

**External authority:** [Google Cloud budgets](https://cloud.google.com/billing/docs/how-to/budgets) — **official vendor guidance; high confidence**. Alerts alone do not cap usage; enforceable controls are required for hard limits.

## 11. Compliance, privacy, and data residency

### 11.1 Organization deletion cleans Postgres only

**Severity:** P1. **Classification:** Documented-but-unimplemented. **Difficulty:** High. **Track D:** Follow-up; must be resolved before claiming erasure completion.

`services/worker/app/tasks/org_deletion.py:1,28-50,88-107` performs Postgres cleanup and marks the job successful. ClickHouse stores organization-linked trace/audit rows (`infra/migrations/clickhouse/000001_create_llm_traces.up.sql:5-39`, `000002_create_mcp_tool_calls.up.sql:5-21`), and MinIO is persistent (`infra/compose/dev/docker-compose.yml:53-64`) without deletion code.

Implement a durable cross-store deletion saga/outbox with per-store checkpoints, retries, inventory, and final absence verification.

**External authority:** [GDPR Articles 5 and 17](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02016R0679-20160504) — **official law; high confidence**.

### 11.2 No legal-hold or retention exception is consulted before deletion

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** High. **Track D:** Follow-up.

Deletion SQL (`org_deletion.py:28-49,65-107`) has no legal-hold or preservation predicate. Job schema `000025_org_deletion_jobs.up.sql:2-13` has no hold/retention fields, and ClickHouse TTLs are unconditional.

Add authorized legal holds, retention-until/exemption fields, hold-aware purge, audit, and lawful-exception procedures.

**External authority:** [EDPB Respect individuals’ rights](https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en) — **official authority; high confidence**.

### 11.3 MCP audit events can be silently lost

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`services/mcp-memory/app/audit.py:156-180` drops events when its bounded queue is full; `:199-242` can drop events during shutdown or sink failure. The ClickHouse table has no delivery status (`infra/migrations/clickhouse/000002_create_mcp_tool_calls.up.sql:5-21`).

Use durable outbox/acknowledged append, retry/dead-letter, deadline-bounded drain, delivery status, reconciliation, and paging on drops.

**External authority:** [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — **official standard; high confidence**.

### 11.4 Audit storage has no tamper-evidence

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

The audit schema has no sequence, hash, signature, or immutable pointer (`000002_create_mcp_tool_calls.up.sql:5-21`); `audit.py:129-146` uses ordinary ClickHouse INSERT and `:111-126` falls back to ordinary logs.

Use append-only credentials, immutable/WORM or signed/hash-chained events, and alteration monitoring.

**External authority:** [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — **official standard; high confidence**.

### 11.5 Raw deletion exceptions are persisted without redaction/lifecycle

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

`org_deletion.py:93-105` logs full exceptions and stores `str(exc)[:500]`; `services/worker/app/logging.py:19-39` serializes formatted exceptions; the job schema has no error retention or masking policy.

Store stable error codes and sanitized summaries; keep detailed diagnostics restricted and short-lived.

**External authority:** [GDPR text](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02016R0679-20160504) and OWASP Logging Cheat Sheet — **official law/standard; high confidence**.

## 12. Testing strategy and quality gates

### 12.1 Python CI gate is not branch-protected

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Low. **Track D:** **Blocker for Python-only changes**.

Python-only paths set `run_python` (`.github/path-filters.yml:2-20`, `.github/actions/detect-changes/action.yml:142-151`). `ci-gate-python` exists (`.github/workflows/ci.yml:2495-2547`), but `.github/branch-protection-main.json:2-10` does not require it.

A Python correctness/security failure can merge while the inactive Go gate passes. Add the Python aggregate to required checks and test gate coverage.

**External authority:** [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) — **official documentation; high confidence**.

### 12.2 Semgrep community/OWASP findings are advisory and unprotected

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Low. **Track D:** **Blocker for security-gated dashboard release**.

`.github/workflows/semgrep.yml:73-95` runs community rules without `--error`; branch protection omits Semgrep, and `ci-gate-security` has no Semgrep dependency (`ci.yml:2471-2493`).

Convert defined severities into failing checks and require the aggregate, while labeling advisory rules separately.

**External authority:** [NIST SSDF](https://csrc.nist.gov/projects/ssdf) and GitHub protected-branch guidance — **official standard/documentation; high confidence**.

### 12.3 CI has no fault-injection or chaos gate

**Severity:** P2. **Classification:** Documented-but-unimplemented. **Difficulty:** High. **Track D:** Follow-up.

`infra/README.md:30-41` defers chaos/load environments. `infra/scripts/e2e-phase35-ci.sh:7-34` and `.github/workflows/ci.yml:1297-1373` test healthy dependencies only; no fault injector is present.

Add deterministic Redis/Postgres/network fault tests and recovery assertions, with longer stochastic runs scheduled.

**External authority:** [Google SRE Testing for Reliability](https://sre.google/sre-book/testing-reliability/) — **official SRE guidance; high confidence**.

### 12.4 Migration CI never executes rollback/down migrations

**Severity:** P2. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** Follow-up.

CI tests forward migration and idempotence (`.github/workflows/ci.yml:439-465`), while `infra/migrations/postgres/cmd/migrate/main.go:33-38` supports down. `migrate_test.go:39-81` checks file pairing but does not execute down SQL.

In disposable Postgres, execute controlled down/up cycles and assert schema/version invariants.

**External authority:** [Google SRE Testing for Reliability](https://sre.google/sre-book/testing-reliability/) — **vendor engineering guidance; medium confidence**.

## 13. Additional staff-engineering concerns

### 13.1 Model-policy enforcement fails open when Postgres is unavailable

**Severity:** P0. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** **Blocker**.

`services/proxy/internal/bootstrap/postgres.go:341-383` constructs `PassthroughRegistry` when `pgDB` is nil and logs that every model is allowed. `packages/modelpolicy/registry.go:57-70` ignores organization ID, and `services/proxy/internal/http/provider_routing_middleware.go:71-80` uses this resolver on the live authenticated chat path.

A database outage or wiring failure changes an authorization decision from deny to permit. Fail closed; if break-glass is retained, require explicit authorization, default deny, alert, and readiness-gate.

**External authority:** [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — **official standard; high confidence**. Authorization must deny by default.

### 13.2 Redis failure removes proxy rate limiting

**Severity:** P2. **Classification:** Documented-but-unimplemented. **Difficulty:** Medium. **Track D:** **Blocker for paid-provider traffic during Redis outage**.

`services/proxy/internal/http/ratelimit_middleware.go:59-90` explicitly fails open on limiter errors. `packages/ratelimit/redis_slider.go:18-51` has no local fallback.

Use conservative local/global emergency caps or fail closed/shed paid traffic and test outage behavior.

**External authority:** [OWASP API4 Unrestricted Resource Consumption](https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/) — **official standard; high confidence**.

### 13.3 Maintenance tasks lack execution deadlines

**Severity:** P1. **Classification:** Undocumented-but-real bug. **Difficulty:** Medium. **Track D:** **Blocker for bounded lifecycle/deletion work**.

`services/worker/app/celery_app.py:59-90` has no global task limits; `tasks/base.py:12-25` has no deadline; `tasks/org_deletion.py:53-109` has no `soft_time_limit` or `time_limit`. Extraction does set limits (`tasks/extraction.py:69-78`), showing this is not a platform-wide default.

A stalled database operation can occupy a maintenance worker indefinitely. Add task-specific soft/hard limits, cancellation-safe network/DB timeouts, retryable terminal state, and alerts.

**External authority:** OWASP API4 — **official standard; high confidence**. Missing execution limits create resource-starvation and denial-of-service risk.

# Master prioritized checklist

## Must fix or explicitly risk-accept before starting/rolling out Track D

1. **P0 — Blocker:** Remove `PassthroughRegistry` on Postgres failure; enforce deny-by-default model policy.
2. **P0 — Security-critical:** Replace lossy model-policy Pub/Sub invalidation with a versioned durable outbox/reconciliation path and fail closed on unknown policy version.
3. **P1 — Blocker:** Prevent plaintext provider-secret retrieval without a narrowly scoped service authorization and close the BYO-provider SSRF boundary identified in the prior cross-cutting audit.
4. **P1 — Blocker:** Make organization deletion cross-store, hold-aware, retryable, and verifiable before reporting success.
5. **P1 — Blocker:** Add durable embedding recovery and a safe tenant-filtered ANN strategy before relying on memory retrieval at scale.
6. **P1 — Blocker:** Replace startup-only readiness and add bounded execution for deletion/maintenance tasks.
7. **P1 — Blocker for Python-only changes:** Protect `ci-gate-python`; make Semgrep security findings that are intended to block merges part of required branch protection.
8. **P1:** Correct exact context budgeting, including provider payload, formatter, tool schemas, and effective available tokens.
9. **P1:** Fix embedding profile/version persistence, concurrent cache-score ordering, and pre-score `max_memories` truncation.
10. **P1:** Fix gRPC cancellation/status semantics and provider/model capability mismatches.
11. **P1:** Define safe idempotency under Redis failure/ambiguous 5xx and repair the broker/database deletion race.
12. **P1:** Add SSE write deadlines, queue load shedding, provider connection caps, fallback routing, and model-scoped breakers.
13. **P1:** Implement tested backup/restore and a production deployment topology before production rollout.

## Safe only as explicitly tracked follow-up work

14. **P2:** Replace mutable RLS bypass GUCs with database-attested service roles; bound auth tombstones; add log redaction and tamper-evident audit storage.
15. **P2:** Make Buf breaking checks required, pin generators, and add real consumer-driven contract tests.
16. **P2:** Add Redis reconnect jitter, fault-injection/chaos tests, rollback execution tests, and realistic capacity breakpoint tests.
17. **P2:** Add cumulative tenant spend/token budgets, worker pool budgets, model lifecycle refresh, image-bound SBOMs, worker scanning, and secret rotation.
18. **P2:** Replace fixed ClickHouse TTLs with policy-controlled retention and legal-hold procedures.
19. **P3:** Reconcile stale documentation only after runtime behavior and release gates are corrected.

## References

[1]: https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/ "OWASP API Security Top 10 API2: Broken Authentication"
[2]: https://www.postgresql.org/docs/current/ddl-rowsecurity.html "PostgreSQL Row Security"
[3]: https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/ "AWS Multi-Tenant Data Isolation with PostgreSQL Row-Level Security"
[4]: https://pkg.go.dev/net/http#ResponseController "Go net/http ResponseController"
[5]: https://sre.google/sre-book/addressing-cascading-failures/ "Google SRE: Addressing Cascading Failures"
[6]: https://go.dev/src/net/http/transport.go "Go net/http Transport Source"
[7]: https://www.w3.org/TR/trace-context/ "W3C Trace Context"
[8]: https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/observability/tracing "Envoy Tracing"
[9]: https://grpc.io/docs/guides/status-codes/ "gRPC Status Codes"
[10]: https://grpc.io/docs/guides/error/ "gRPC Error Handling"
[11]: https://buf.build/docs/breaking/ "Buf Breaking Change Detection"
[12]: https://buf.build/docs/bsr/remote-plugins/usage/ "Buf Remote Plugins"
[13]: https://docs.pact.io/ "Pact Consumer-Driven Contract Testing"
[14]: https://learn.microsoft.com/en-us/azure/architecture/patterns/retry "Azure Retry Pattern"
[15]: https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker "Azure Circuit Breaker Pattern"
[16]: https://platform.openai.com/docs/deprecations "OpenAI Deprecations"
[17]: https://docs.anthropic.com/en/docs/about-claude/models/overview "Anthropic Models Overview"
[18]: https://developers.openai.com/api/docs/guides/token-counting "OpenAI Token Counting"
[19]: https://platform.claude.com/docs/en/build-with-claude/context-windows "Anthropic Context Windows"
[20]: https://qdrant.tech/documentation/tutorials-operations/embedding-model-migration/ "Qdrant Embedding Model Migration"
[21]: https://redis.io/docs/latest/develop/using-commands/transactions/ "Redis Transactions"
[22]: https://docs.pinecone.io/guides/search/rerank-results "Pinecone Reranking"
[23]: https://sre.google/sre-book/data-integrity/ "Google SRE: Data Integrity"
[24]: https://www.postgresql.org/docs/current/sql-createindex.html "PostgreSQL CREATE INDEX"
[25]: https://github.com/pgvector/pgvector "pgvector Documentation"
[26]: https://redis.io/docs/latest/develop/pubsub/ "Redis Pub/Sub"
[27]: https://www.usenix.org/system/files/atc19-pang.pdf "Zanzibar: Google’s Consistent, Global Authorization System"
[28]: https://microservices.io/patterns/data/transactional-outbox.html "Transactional Outbox Pattern"
[29]: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ "AWS Making Retries Safe with Idempotent APIs"
[30]: https://docs.stripe.com/api/idempotent_requests "Stripe Idempotent Requests"
[31]: https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/ "Kubernetes Rolling Updates"
[32]: https://csrc.nist.gov/pubs/sp/800/218/final "NIST Secure Software Development Framework"
[33]: https://slsa.dev/spec/v1.0/faq "SLSA FAQ"
[34]: https://kubernetes.io/docs/concepts/configuration/secret/ "Kubernetes Secrets"
[35]: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/ "Kubernetes StatefulSets"
[36]: https://docs.sqlalchemy.org/en/latest/core/pooling.html "SQLAlchemy Connection Pooling"
[37]: https://redis.io/docs/latest/develop/reference/eviction/ "Redis Eviction"
[38]: https://cloud.google.com/billing/docs/how-to/budgets "Google Cloud Budgets"
[39]: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02016R0679-20160504 "General Data Protection Regulation"
[40]: https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en "EDPB Respect Individuals’ Rights"
[41]: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html "OWASP Logging Cheat Sheet"
[42]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches "GitHub Protected Branches"
[43]: https://csrc.nist.gov/projects/ssdf "NIST Secure Software Development Framework Project"
[44]: https://sre.google/sre-book/testing-reliability/ "Google SRE: Testing for Reliability"
[45]: https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/ "OWASP API4: Unrestricted Resource Consumption"
[46]: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html "OWASP Authorization Cheat Sheet"
