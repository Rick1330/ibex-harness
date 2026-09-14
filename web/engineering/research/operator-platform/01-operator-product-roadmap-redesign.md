# ibex-harness Operator Product Roadmap Redesign

**Decision basis.** This roadmap synthesizes the specialist research against repository evidence at main commit `9b0793d6e59bed16f69215112c9f0d9a737622aa`, with the user’s statement that **4.C.5 is complete** treated as the current planning baseline; any remaining 4.C.5 verification is a release-evidence gate rather than a reason to discard the completed work. It distinguishes present evidence from planned behavior. A roadmap statement, migration, permission bit, or test file is not treated as an implemented product capability unless a live contract and acceptance evidence exist.

## Executive recommendation

Do not start the current Track D as a frontend build. The repository currently deploys a documentation-oriented Next.js site as static assets: `web/next.config.mjs:9-17` enables static export, and `.github/workflows/web-deploy.yml:52-61,97-112` builds `web/out` and uploads it to Cloudflare Pages. The API has bearer-token validation and CRUD routers, but `services/api/app/main.py:117-139` has no session/refresh or SSE router. Track D instead promises an authenticated, stateful, tenant-scoped, realtime operator product. Static export cannot supply cookie-backed dynamic behavior or a long-lived server endpoint [1] [2] [3].

Create **Track P — Operator Readiness, Evidence, and Control Plane** as a new prerequisite track before any Track D UI milestone. Track P establishes the runtime topology, identity and tenant boundary, versioned API/SSE contracts, canonical evidence model, durable event publication, privacy and deletion controls, auditability, and production operations. No dashboard screen is release-ready until Track P gates pass.

Redesign Track D into thin, end-to-end capability slices, each containing backend contracts, UI behavior, tests, telemetry, and rollback. The recommended order is:

1. **P0–P6:** runtime, identity, contract, evidence, governance, and production gates.
2. **D1:** operator shell and overview using real authenticated read models.
3. **D2:** global Explore and provenance Trace Inspector.
4. **D3:** sessions, memory, context, and replay-safe evidence.
5. **D4:** failures, incidents, and evidence bundles.
6. **D5:** directives, routing decisions, experiments, and controlled actions.
7. **D6:** usage, cost governance, and capacity controls.
8. **R:** staged release readiness, canary, supportability, and final governance closure.

The differentiated product wedge is not a generic APM dashboard. It is an **auditable context-and-policy provenance debugger**: an operator can explain why an agent acted by traversing session, trace, checkpoint, retrieval, memory, directive, tool, provider fallback, evaluation, and rollout evidence, while every sensitive field, tenant boundary, deletion action, and operator mutation is governed.

## Current-state diagnosis

### What exists

The repository has meaningful foundations. It has FastAPI resource routers for organizations, users, agents, tokens, providers, rate limits, and model policies. It has Postgres session/checkpoint migrations, ClickHouse LLM and MCP metadata tables, memory relationships, directive storage, permission constants, OTel-related plumbing, migration smoke tests, evaluation workers, and a planned dashboard information architecture. The user also states that 4.C.5 streaming hardening is complete; that work should be retained as a prerequisite rather than discarded.

### What does not exist as a dashboard-ready product

The live application has no authenticated operator route, no session/refresh flow, no SSE API, no memory/directive/session/trace/drift/analytics/billing/export/deletion read model, and no published dashboard-grade OpenAPI contract. Permission names such as `directive`, `session`, `trace:read`, and `trace:export` are not HTTP contracts. The existing web routes are public site pages under `web/src/app/(site)` and `web/src/app/docs`, not an operator application.

The trace store is an aggregate request record. `packages/clickhouse/record.go:10-37` and `infra/migrations/clickhouse/000001_create_llm_traces.up.sql:5-39` have no `span_id`, `parent_span_id`, operation kind, tool/retrieval/memory events, event sequence, or prompt/completion content. The 90-day ClickHouse TTL is storage hygiene, not a deletion SLA. MCP tool-call rows lack session, checkpoint, trace, event, and schema-version joins. Consequently, the current data cannot support a trustworthy causal Trace Inspector or durable postmortem evidence bundle.

The roadmap’s claim that `usage_counters`, `tier_limits`, and `billing_events` already exist is contradicted by the repository. `infra/migrations/postgres/000028_rate_limit_overrides.up.sql` contains RPM overrides only, while Track B explicitly defers monthly token spend and usage dashboards. D3 has a relationship schema but no memory management API. D4 has directive storage and permission constants but no directive lifecycle API, drift-alert API, MFA flow, or Phase 4.5 fingerprinting contract.

Production readiness is also not executable. The architecture describes Kubernetes, Helm, ArgoCD, Terraform, canaries, backup retention, and digest-pinned images, but live-tree inspection found no Kubernetes/Helm/Kustomize deployment manifests or admission verification. `/health` is unconditional and `/ready` reports only application readiness state; no manifest wires startup, liveness, readiness, drain, resource, or rollback behavior. There is no demonstrated backup/restore drill, RPO/RTO gate, durable outbox, cross-store deletion receipt, or required Playwright dashboard job.

### Blockers versus follow-up

| Classification | Items | Decision rule |
|---|---|---|
| **Blockers** | Runtime topology; authenticated tenant context; versioned API/SSE contracts; trace/span/event identity; durable publication; privacy/redaction; deletion and retention; audit ledger; production deployment and recovery; cross-tenant tests; required E2E/accessibility gates | Track D UI or production launch cannot pass until evidence is signed |
| **Follow-up after first usable slice** | Saved views; incident notifications and external sinks; advanced graph layouts; self-serve experiments; multi-region residency; extension SDK; richer content capture; automated anomaly clustering | May proceed in parallel only with explicit risk owner and no claim of completeness |

## Retain, split, retire: existing 4.D.1–4.D.5

| Existing milestone | Decision | Keep | Split or retire | Replacement acceptance
|---|---|---|---|
| **4.D.1 Dashboard foundation, auth, realtime** | **Split and resequence** | Navigation intent, authenticated shell concept, org switch, reconnecting client, accessibility intent | Retire the five-day promise and separate runtime/auth/API foundation from shell; do not count docs pages or benchmark charts as dashboard work | A live operator origin, validated session/refresh, tenant context, versioned API client, SSE `Last-Event-ID` behavior, reconnect/backoff, required CI job, and four-role fixtures exist before shell sign-off [4] [5] |
| **4.D.2 Trace Inspector** | **Retain the product wedge; split data from UI** | Summary, context assembly, conversation, tools, raw/redacted evidence, cross-links, golden trace, page-load target | Replace flat ClickHouse-row assumption with canonical trace/span/event ingestion, query API, evidence policy, and trace-to-resource identity | Nested multi-step fixture is queryable; every displayed conclusion links to source evidence; missing/sampled/deleted evidence is marked; raw access is policy-gated and audited |
| **4.D.3 Memory Browser v2** | **Split backend management from graph UI** | Search, retained table, graph lineage, GDPR preview/export/delete | Do not treat `memory_relationships` SQL as a management API; make deletion asynchronous, tenant-scoped, auditable, and retryable | Cascade preview equals executed deletion scope; export/delete status is observable; cross-tenant and retry tests pass [6] |
| **4.D.4 Drift alerts and directive management** | **Split into directive control plane and Phase 4.5 drift integration** | Immutable directive versions, diff, promotion, revoke, alert grouping, anti-fatigue UX | Move drift UI out of Phase 4 exit unless fingerprinting emits a versioned contract; add step-up MFA and audit before mutation | Directive lifecycle state machine, promotion/revoke, regression linkage, step-up assurance, audit, and separate drift-alert producer contract |
| **4.D.5 Analytics v2 and cost governance** | **Split ledger/control plane from analytics UI** | Cross-provider usage charts, thresholds, hard pause concept | Retire the false premise that billing schema already exists; usage and budget enforcement cannot be chart-first | Immutable usage facts, rate-card version, idempotent aggregation, alert state, proxy authorization hook, and a negative test proving hard caps deny requests [7] |

The completed 4.C.5 work should be retained, but realtime acceptance remains blocked until its bounded queue/write-timeout/resource budget and provider-error normalization are evidenced. Existing accumulators, metrics, disconnect cleanup, and tests are valuable. Add slow-client, memory, goroutine, and provider-fixture soak tests before D1/D2 realtime sign-off.

## New prerequisite track: Track P — Operator Readiness, Evidence, and Control Plane

**Purpose.** Track P converts architectural intent into enforceable contracts. It is complete only when an authenticated operator can safely query real, tenant-scoped, redacted evidence through a live runtime and the platform can publish, retain, delete, restore, audit, and roll back that evidence. Track P is a table-stakes gate, not a hidden implementation detail.

### P0. Runtime topology and environment decision

**Outcome.** A chosen deployment topology supports a server-capable operator UI or a static SPA with a separately deployed API/SSE origin.

**Scope and deliverables.** Record the decision in an ADR. Provision local, preview, staging, and production origins. Define TLS, CORS, CSRF, cookie domain, token audience, refresh rotation, SSE ingress timeouts, reverse-proxy buffering, environment configuration, and observability. Create a minimal health, readiness, drain, and SSE probe.

**API/data/UX implications.** All subsequent links use stable origin-aware URLs. The client knows live versus historical mode and shows connection, freshness, lag, and reconnect state. The API contract identifies version, tenant, pagination, error envelope, and stream semantics.

**NFR and verification.** Static export is not used for authenticated realtime behavior. A staging smoke test proves login, API call, SSE connect, reconnect with `Last-Event-ID`, and graceful drain. Browser and API origins reject unauthorized cross-origin requests.

**Rollout/rollback.** Deploy the operator origin dark, behind an internal flag. Roll back by routing traffic to the static site and disabling operator-origin DNS or feature access without changing stored data.

**Why it exists.** Without this decision, the current 4.D.1 foundation is impossible to schedule and every UI estimate is misleading.

### P1. Identity, tenancy, authorization, and session assurance

**Outcome.** Every operator request, stream, export, action, and asynchronous job has a verified tenant and policy decision.

**Scope and deliverables.** Implement login/session or OIDC federation, refresh rotation and revocation, recent-authentication context, tenant membership, org switching, role and permission evaluation, resource classification, and deny-by-default actions: metadata read, redacted-content read, raw-content read, export, delete, replay, secret use, policy change, and break-glass. Define MFA/step-up and dual approval for deletion, raw/export access, production replay, secret changes, and break-glass.

**API/data/UX implications.** Use typed authorization errors without leaking object existence. Add actor, tenant, purpose, assurance, and policy-decision fields to audit events. The UI exposes only allowed actions, explains denied actions, and never displays provider keys or bearer tokens.

**NFR and verification.** Matrix-test two tenants across API, Postgres/RLS, Redis keys, ClickHouse filters, object storage, queues, exports, and replay artifacts. Assert normal dashboard DB roles are not superusers or `BYPASSRLS`. Test guessed IDs, tenant switching, revoked sessions, degraded IdP, expired step-up, and cross-tenant negative paths [8] [9].

**Rollout/rollback.** Start with internal operators and read-only metadata. A kill switch disables sensitive actions. Roll back policy versions, not audit history.

**Why it exists.** A valid admin token is not sufficient authorization for raw evidence, deletion, secrets, or replay.

### P2. Canonical evidence model, correlation, and durable publication

**Outcome.** A multi-step agent run is represented as a versioned, queryable, replay-aware evidence graph.

**Scope and deliverables.** Define an OTel/W3C-compatible envelope containing `event_id`, `source`, `schema_version`/`dataschema`, `trace_id`, `span_id`, `parent_span_id`, links, `org_id`, `agent_id`, `session_id`, `turn_id`, `request_id`, `checkpoint_id`, sequence, timestamps, operation kind, status/error, resource/scope, attributes, capture policy, sample decision, and payload references. Add typed provenance for model calls, prompt references, tool definitions/calls/results, retrieval candidates and scores, memory reads/writes, context assembly, directives, routing decisions, fallbacks, evaluations, and deployment versions. Return checkpoint IDs from writes and require non-null joins for checkpoint-backed traces.

Add a Postgres transactional outbox written with the aggregate: `event_id`, `aggregate_id`, monotonic `aggregate_seq`, schema version, occurred time, payload digest, delivery status, and retry metadata. Relay idempotently to ClickHouse, Redis Streams, and encrypted object storage. Define batch limits, partial failure, replay position, dedupe, pending-entry reclamation, poison-message handling, and per-aggregate ordering [10] [11].

**API/data/UX implications.** Publish versioned OpenAPI for trace tree, session timeline, span/event search, scores, metrics, and SSE envelopes. Use cursor pagination, bounded time ranges, query budgets, stable sequence order, and explicit completeness metadata. Deep links preserve query, columns, time range, and tenant.

**NFR and verification.** Ingest a synthetic run with agent, retrieval, memory, tool, retry, fallback, and evaluation spans. Prove parent/child identity, duplicate safety, crash-after-commit, crash-before-ack, replay, partial trace, unknown attribute round-trip, and old/new consumer compatibility.

**Rollout/rollback.** Dual-write only during a measured compatibility window. Keep the aggregate legacy projection as a derived read model. Roll back consumers, not committed event identity; replay from the outbox.

**Why it exists.** A flat request row cannot explain causality, support trace-to-resource navigation, or safely power D2.

### P3. Privacy, retention, deletion, audit, and safe rendering

**Outcome.** Evidence is useful without reversing the repository’s existing no-prompt/no-completion security boundary.

**Scope and deliverables.** Define none, metadata-only, redacted, and full capture per tenant, field, environment, and event kind. Redact before queueing or exporting. Store sensitive payloads only in encrypted object storage with manifest, retention class, masking policy version, and digest. Add tenant/project retention policies, purge schedules, delete-by-trace/session/org, export-before-delete, legal hold, tombstones, per-store watermarks, deletion receipts, and recomputation or tombstoning of aggregates. Add a restricted append-only audit ledger with actor, authenticator/session, purpose, policy result, object, fields, approval, before/after hashes, and correlation IDs.

Make prompts, outputs, tool arguments, links, HTML, Markdown, and model-suggested commands inert escaped data. Use strict CSP and safe URL handling. Add an `evidence_bundle` with immutable manifest, deployment image digests, migrations, model/directive/policy hashes, linked IDs, redacted references, chain-of-custody, retention tier, and signed export.

**NFR and verification.** Masked-by-default fixtures prove secrets never reach ClickHouse, OTLP, logs, dead-letter queues, or browser actions. Deletion tests prove normal query paths return no data after completion and retries are safe. Injection fixtures contain hidden instructions, HTML, links, and cross-tenant identifiers. Audit writes are tamper-evident and read-restricted [12] [13] [14].

**Rollout/rollback.** Begin metadata-only. Enable redacted fields per tenant after policy review. Raw capture is opt-in, time-limited, non-exportable by default, and independently killable. Deletion is never rolled back; restore requires a new governed import.

**Why it exists.** GDPR erasure, incident reconstruction, and safe debugging require a coordinated data-lifecycle contract, not a ClickHouse TTL or confirmation dialog.

### P4. Query, aggregation, freshness, and cost data platform

**Outcome.** Dashboard reads are stable, bounded, explainable, and reconciled.

**Scope and deliverables.** Define a shared query grammar for traces, sessions, failures, memory, and usage with typed fields, operators, AND/OR/NOT, time range, status, agent, model/provider, error, IDs, facets, autocomplete, saved view representation, and cursor pagination. Define ClickHouse query shapes and keys for org/time, agent/session, event point lookup, run reconstruction, tool correlation, and cost aggregation. Add usage ledger facts keyed by org, agent, provider, model, request/run, time, token class, tool units, latency, status, and fallback. Add versioned rate cards, currency, estimate/actual state, budget period, allow/deny/degrade decision, and reconciliation jobs.

**API/data/UX implications.** Queries are URL-serializable and server-side. The UI labels live versus retained data, ingestion lag, retention boundary, matched versus displayed/sample counts, and last updated time. Costs show source facts, rate-card version, and policy version.

**NFR and verification.** Filters apply before pagination. Shared links reproduce exact results. High-cardinality identifiers remain structured event fields, not metric labels or stream partitions. EXPLAIN plans, p95/p99 query targets, bounded memory, sampling-bias disclosure, aggregate-to-raw reconciliation, duplicate retry billing tests, and hard-cap denial tests are required [15] [16].

**Rollout/rollback.** Start with read-only aggregates and shadow reconciliation. Enable enforcement only after ledger parity and proxy negative tests. Roll back rate-card or policy version, never mutate immutable usage facts.

**Why it exists.** A chart over request counts is not cost governance, and ad hoc client filtering cannot scale to operator workloads.

### P5. Production platform, recovery, and supply chain

**Outcome.** The operator system is deployable, recoverable, observable, and promotable.

**Scope and deliverables.** Commit executable manifests or Helm/Kustomize overlays for UI, API, workers, relays, ClickHouse, Redis, and dependencies. Pin image digests. Wire startup/liveness/readiness probes, drain behavior, requests/limits, ephemeral storage, autoscaling bounds, worker concurrency, queue-depth scaling, namespace quotas, migration ordering, rollout status, canary/blue-green, automatic abort, and rollback. Add encrypted off-cluster Postgres base backups plus WAL/PITR, restore scripts, backup freshness alerts, evidence-bundle recovery, and measured RPO/RTO. Generate and verify SBOM, provenance, signatures, migration artifacts, builder identity, and deployed digest using CI and admission.

**API/data/UX implications.** Operators see dependency health, last backup, last restore drill, retention horizon, ingestion lag, DLQ depth, and degraded-mode state.

**NFR and verification.** A clean-environment restore meets declared RPO/RTO and preserves tenant isolation. Load and chaos tests cover peak plus headroom, Redis/ClickHouse/Postgres degradation, provider failure, slow consumers, queue saturation, and rollback. SLOs use latency percentiles, availability, error rate, throughput, queue lag, and cost budgets [17] [18] [19].

**Rollout/rollback.** Promote dark, then staging, then canary. Roll back by digest and known-good migration-compatible version. Never roll back a migration without its compatibility procedure.

**Why it exists.** Architecture prose and signed artifacts do not prove that the product can be deployed, recovered, or safely stopped.

### P6. Contract and assurance harness

**Outcome.** Every capability is independently verifiable and release evidence is machine-generated.

**Scope and deliverables.** Generate the TypeScript SDK from OpenAPI in CI. Add schema snapshots, old/new consumer fixtures, migration-from-zero and upgrade tests, golden trace/session/memory/cost fixtures, OTel round-trip tests, tenant matrix tests, axe and keyboard checks, Playwright with four roles and multiple tenants, trace/report uploads, k6 scenarios, and named SLO/error-budget gates. Make Playwright browser installation and the dashboard environment explicit; the current one-Chromium local-dev config and static-site smoke test are insufficient.

**NFR and verification.** Required checks include API contract, authorization, pagination, redaction, freshness, Last-Event-ID, accessibility, query budgets, p95/p99, failure injection, and no-check fail-closed evaluation.

**Rollout/rollback.** Evidence artifacts are immutable and tied to commit, image digest, schema version, and environment. A failed gate blocks promotion; it does not silently downgrade to public-site smoke tests.

**Why it exists.** A test file or planned route is not an acceptance gate until CI executes it against the intended topology and data.

## Redesigned Track D: operator capability slices

### D1. Authenticated shell and operational overview

**Outcome.** An authorized operator can enter the product, select one organization, see system freshness and current health, and navigate to every investigation surface.

**Dependencies.** P0, P1, P2 query subset, P3 redaction defaults, P6.

**Deliverables.** Implement the separate operator application, org/role context, Overview, Agents/Resources, Explore, Incidents, Settings, navigation breadcrumbs, global search entry, connection status, live/historical selector, and empty/error/partial-data states.

**API/data/UX implications.** Consume generated SDK endpoints only. Use URL state for org, time range, filters, and saved columns. Do not expose mutation controls beyond approved read-only actions.

**NFR and gates.** Four-role and two-tenant Playwright flows; keyboard navigation; axe; p95 initial read under the agreed budget; no cross-tenant leakage; SSE reconnect tested.

**Rollout/rollback.** Internal allowlist and read-only flag; disable route access without removing evidence.

**Why it exists.** It proves the runtime and operator context before specialized screens consume deep data.

### D2. Explore and provenance Trace Inspector

**Outcome.** An operator can answer why an agent acted without first choosing an agent or session.

**Dependencies.** P2 canonical evidence; P3 field policy; P4 query; D1; completed 4.C.5 gates.

**Deliverables.** Global query bar with autocomplete, facets, saved-view-ready URL grammar, trace/session/failure results, three-level progressive disclosure, timeline/flame graph, context assembly, memory score vectors, directive and routing decision, tools, model/fallback, evaluation links, redacted JSON, copy-link, and bidirectional pivots.

**API/data/UX implications.** Use a stable Trace/Span DTO with org-enforced server scope, copyable IDs, request/session/checkpoint/provider IDs, completeness, sampling, freshness, retention, and provenance links. Keep list filters when opening side panel or full detail.

**NFR and gates.** Golden multi-step trace; point lookup by known IDs; cross-tenant 404/empty; sensitive content absent by default; keyboard-safe panel; query and page-load budgets; live selection freezes before detail.

**Rollout/rollback.** Metadata-only launch, then redacted provenance. Disable content expansions or new event kinds by feature flag; retain aggregate read path.

**Why it exists.** This is the product wedge and the first operator-visible proof of the evidence model.

### D3. Sessions, memory, context, and safe replay evidence

**Outcome.** An operator can reconstruct a conversation turn, see retrieval and memory provenance, and export or delete governed data.

**Dependencies.** P2 checkpoint join, retrieval-version contract, P3 lifecycle, D2.

**Deliverables.** Session timeline with stable sequence, memory search/list/detail, bounded graph lineage, context pack breakdown, retrieval snapshot, cascade preview, asynchronous export/delete jobs, deletion receipt, and replay-safe evidence view. Secure replay is not ordinary idempotency replay: it requires immutable source snapshot, explicit versions, sandbox, disabled/mocked tools, no writes or secrets, approval, diff, and separate audit trace.

**NFR and gates.** Preview equals execution; deleted data is absent from all normal queries; missing/redacted/sampled events are explicit; stable tie ordering; embedding/ranking mismatch errors; no production side effects.

**Rollout/rollback.** Read-only first; export/delete by privileged allowlist; disable replay independently.

**Why it exists.** Memory and session pages are only trustworthy when they can prove what was used and what deletion actually removed.

### D4. Failures, incidents, and evidence bundles

**Outcome.** An operator can triage a failure, assign ownership, preserve evidence, and produce a postmortem-ready bundle.

**Dependencies.** P2 events, P3 audit/evidence bundle, P4 query, D2.

**Deliverables.** Failure projection distinct from the insert-only `failed_tasks` table; incident state machine; severity, owner, assignment, dedupe key, timeline, linked traces/sessions/requests, redacted evidence, comments/activity, notifications as a later integration, and signed bundle export.

**NFR and gates.** Every transition is idempotent and audited; raw traceback is gated; incident list filters by status/severity/owner/time; bundle reconstructs evidence after normal telemetry expiry without secrets or cross-tenant data.

**Rollout/rollback.** Triage projection is read-only first. Incident mutations have action ledger and rollback for assignment/state, not deletion of history.

**Why it exists.** A dead-letter row is not an incident workflow, and 90-day metadata cannot alone support high-quality postmortems.

### D5. Directives, routing decisions, experiments, and controlled actions

**Outcome.** Operators can understand and safely change policy with preview, approval, provenance, and rollback.

**Dependencies.** P1 step-up; P3 audit; P2 routing decision; D2/D4; Phase 4.5 fingerprinting for drift.

**Deliverables.** Immutable directive versions, diff, promotion/revoke state machine, regression-run linkage, matched policy revision, ordered candidates and rejection reasons, capability-catalog version, provider credential scope, fallback trigger, experiment assignment/exposure/holdback, guardrails, kill switch, operator action ledger, dry-run preview, bounded rollout, and rollback pointer.

**NFR and gates.** Replaying recorded inputs with recorded versions yields the same decision. Sensitive changes require phishing-resistant MFA or equivalent step-up; high-impact changes can require dual approval. Duplicate submits are safe; blast radius is shown before confirmation; every action is auditable.

**Rollout/rollback.** Dark launch, 1% shadow, 10%, 25%, then 100% only after minimum sample and bake windows. Automated abort on quality, latency, error, safety, or cost guardrail breach.

**Why it exists.** The current provider/policy mutations have no action journal, approval, preview, rollback, or decision provenance.

### D6. Usage, cost governance, and capacity

**Outcome.** Operators can explain spend and enforce budgets without double charging or relying on ephemeral counters.

**Dependencies.** P2 durable facts, P4 ledger and query, P5 resource controls, D1/D2.

**Deliverables.** Usage ledger, versioned rate cards, provider/model/fallback attribution, rollups, budget scopes and periods, alert state, hard pause/degrade decisions, Redis hot counters with reconciliation, worker concurrency and queue dashboards, resource/cost ceilings, and exportable cost evidence.

**NFR and gates.** Idempotent ingestion; raw-to-aggregate reconciliation; retry does not double charge; policy-version replay; hard cap blocks proxy requests; high-cardinality query remains bounded; live and historical spend carry completeness labels.

**Rollout/rollback.** Shadow ledger and alert-only mode; then soft limits; then hard enforcement per tenant. Roll back policy/rate-card version while preserving ledger facts.

**Why it exists.** Analytics becomes governance only when persisted facts can change authorization decisions and prove the result.

## Phase gates before any UI

| Gate | Must be true | Evidence artifact |
|---|---|---|
| **G0 topology** | Live operator origin/API/SSE design is chosen and staged | ADR, environment matrix, smoke transcript |
| **G1 identity** | Tenant, role, session, step-up, revocation, and negative paths work | Authorization matrix and two-tenant test report |
| **G2 contract** | OpenAPI, SSE, event envelope, DTOs, SDK generation, compatibility rules are versioned | Spec snapshot, generated client, contract fixtures |
| **G3 evidence** | Nested trace/event graph, checkpoint join, outbox, replay, idempotency work | Golden run, outbox crash/replay report, OTel round-trip |
| **G4 governance** | Capture policy, redaction, audit, retention, deletion, safe rendering are enforced | Data inventory, deletion manifest, injection/redaction tests |
| **G5 platform** | Deploy, probes, rollback, backup/restore, supply-chain verification work | Staging rollout, restore drill, provenance/admission report |
| **G6 assurance** | Required Playwright/axe/keyboard, load, chaos, and SLO gates are required in CI or named environment | Signed CI and performance evidence bundle |

If any gate fails, the result is a blocker or an explicitly approved residual risk. It is not converted into a UI-only follow-up.

## Critical path and parallel work

**Critical path:** P0 → P1 → P2 → P3 → P4/P5/P6 → D1 → D2 → D3/D4 → D5/D6 → R. P4 query and P5 production controls can proceed in parallel after P2. P6 can begin with fixtures at P2 and must mature before D1. D3 and D4 can run in parallel after D2. D5 requires P1/P3 and the Phase 4.5 drift producer. D6 can build ledger and reconciliation in parallel with D2 but cannot enable hard caps before P4 and proxy integration.

**Parallel work that does not bypass gates:**

| Stream | Parallel work | Constraint |
|---|---|---|
| Contracts | OTel envelope, retrieval versioning, evaluation score model, routing-decision schema | Must converge in P2 schema registry and compatibility tests |
| Platform | Manifests, backup/PITR, supply chain, probes, resource budgets | Must pass P5 before production data |
| Assurance | Golden fixtures, Playwright harness, axe/keyboard, k6/chaos | Must target the chosen topology and be required by P6 |
| UX | IA, query grammar, progressive disclosure, accessibility prototypes | May use fixtures but cannot claim real-data completion before P2/P3 |
| Product | Incident workflow, evidence bundles, saved views, extension SDK | Follow-up unless dependencies are explicitly promoted |

## Required data contracts and platform capabilities

| Contract/capability | Minimum fields or behavior | Consumer |
|---|---|---|
| **Operator session** | Subject, tenant membership, role, permissions, assurance, issued/expiry/revocation, refresh rotation | Every operator API/SSE action |
| **Trace/span/event** | W3C IDs, parent/links, org, agent, session, turn, request, checkpoint, sequence, operation kind, status, error, resource, schema, capture/sample decision | Explore, sessions, incidents, evaluation |
| **Provenance events** | Prompt reference/hash, model parameters/usage, tool definition/call/result, retrieval candidates/score/rank, memory read/write, context assembly, directive, routing/fallback | Trace Inspector, replay evidence |
| **Outbox event** | Event/source identity, aggregate/sequence, schema, digest, occurrence, delivery, retry, dedupe | ClickHouse, Redis, object store |
| **Query contract** | Typed grammar, URL serialization, facets/autocomplete, bounded ranges, cursor, sort, freshness/completeness | All data-heavy screens |
| **Evaluation score** | Target, evaluator name/version, value/type, rationale, source, dataset/experiment/run, idempotency key | D4/D5 promotion |
| **Usage/cost fact** | Actual provider/model, token classes, tool units, status, rate card/version, currency, cost state, budget decision | D6 and proxy |
| **Deletion lifecycle** | Tombstone, policy, legal hold, per-store watermarks, job status, receipt, audit, retry | D3/D4 and compliance |
| **Operator action** | Actor, intent, before/after diff, approval, idempotency, result, rollback pointer, incident/evidence link | D5 and governance |
| **Evidence bundle** | Immutable manifest, linked IDs, versions/digests, redacted payload refs, chain of custody, retention/legal hold, signature | Incidents, support, postmortems |

## Differentiated world-class product wedge

The winning position is **Explainable Agent Operations**. A generic observability tool answers where latency or errors occurred. ibex-harness should answer **why the agent selected this context, directive, tool, provider, and fallback, what evidence supports that explanation, what changed between runs, and whether an operator can safely act**.

The wedge has five reinforcing properties. First, it is provenance-first: memory score vectors, retrieval versions, directive hashes, routing decisions, tool results, and evaluator evidence are linked rather than inferred. Second, it is investigation-first: Explore is global, high-cardinality, URL-shareable, and preserves context across pivots. Third, it is safety-first: metadata and redacted evidence are default; raw access, replay, deletion, and policy mutation are step-up, audited, and bounded. Fourth, it is governance-first: every promotion, budget decision, deletion, and incident bundle is reproducible from immutable versions. Fifth, it is honest about uncertainty: sampled, missing, expired, redacted, and fail-open telemetry is visibly labeled. This is differentiated from a generic APM clone while remaining interoperable with OpenTelemetry [20] [21].

## Risks and open decisions

| Risk or decision | Required resolution | Owner and timing |
|---|---|---|
| Operator runtime topology | Separate server-capable app or static SPA plus live API/SSE origin | Architecture; before P0 exit |
| Session and identity model | Cookie/session versus OIDC bearer exchange, refresh rotation, tenant claims, MFA assurance | Security/identity; P1 |
| Trace storage strategy | Extend ClickHouse, introduce event store, or use dual projections; define query and deletion trade-offs | Data platform; P2/P4 |
| Content capture | Metadata-only default versus tenant-approved redacted/full fields; exporter guarantees | Security/privacy; P3 |
| Retention and legal hold | Dataset classes, DSAR scope, backups, media, scores, evidence bundles | Privacy/legal; P3/P5 |
| Drift producer | Pull Phase 4.5 fingerprinting forward or defer drift UI | Product/ML platform; before D5 |
| Replay semantics | Sandbox, tool mocks, model/provider version pinning, side-effect policy, approval count | Security/product; D3/D5 |
| Cost source of truth | Postgres ledger plus ClickHouse projection; Redis only as hot counter | Finance/platform; P4/D6 |
| Residency and regions | Home region, provider egress, support access, backup/failover semantics | Enterprise architecture; before regulated launch |
| Availability and completeness | Fail-open versus fail-closed trace writes, operator labels, alert thresholds | SRE/product; P2/P5 |
| Release policy | Canary sample/time, abort thresholds, on-call, rollback owner, evidence retention | Release/SRE; R |
| Extension model | Read-only export/webhooks first; no arbitrary runtime code in control plane | Platform; post-D5 |

## Master checklist

### Before any dashboard UI

- [ ] Record runtime topology and provision live UI/API/SSE environments.
- [ ] Define TLS, CORS, CSRF, cookie/token, refresh, SSE timeout, buffering, and drain policy.
- [ ] Implement tenant-scoped identity, org switching, revocation, role/permission evaluation, and step-up assurance.
- [ ] Prove two-tenant isolation through API, Postgres, Redis, ClickHouse, object storage, queues, exports, and replay.
- [ ] Publish versioned OpenAPI, SSE envelopes, error model, pagination, and generated client.
- [ ] Define OTel/W3C trace identity, conversation/session identity, checkpoint join, event sequence, and schema registry.
- [ ] Implement transactional outbox, idempotent relays, replay positions, ordering, and poison-message handling.
- [ ] Define capture, redaction, retention, deletion, legal hold, audit, safe rendering, and evidence-bundle policy.
- [ ] Implement executable deployment manifests, probes, drain, limits, autoscaling, migrations, canary, rollback, and admission verification.
- [ ] Implement encrypted backup/PITR and run a measured clean-environment restore drill.
- [ ] Make Playwright, axe, keyboard, contract, load, chaos, and SLO gates required in the intended environment.

### Before D1/D2 release

- [ ] Authenticate real operators and seed four roles and multiple tenants.
- [ ] Query a nested golden run with retrieval, memory, tool, fallback, and evaluation evidence.
- [ ] Verify URL-shareable query state, facets, pagination-before-filter behavior, freshness, retention, sampling, and completeness labels.
- [ ] Verify progressive trace disclosure, focus management, screen-reader announcements, non-color status, and no keyboard traps.
- [ ] Verify raw fields remain hidden, redacted, audited, and non-exportable by default.
- [ ] Verify 4.C.5 bounded queue/write timeout, provider normalization, slow-client soak, and leak tests.

### Before D3–D6 controls

- [ ] Prove deletion preview equals execution and all stores converge to the tombstone.
- [ ] Prove secure replay has no production side effects and emits a separate trace/audit record.
- [ ] Prove incident transitions, operator actions, approvals, and rollback pointers are idempotent and auditable.
- [ ] Prove routing/policy decisions reproduce from recorded versions.
- [ ] Prove evaluation scores link to traces/spans and promotion evidence snapshots.
- [ ] Prove usage ledger reconciliation, fallback attribution, retry dedupe, budget alerts, and hard-cap denial.
- [ ] Prove resource, queue, DLQ, and cost ceilings under load and chaos.

### Before production default-on

- [ ] Complete dark launch and staged 1%/10%/25%/100% promotion with bake windows.
- [ ] Define and meet SLOs, error budgets, capacity headroom, recovery objectives, and cost limits.
- [ ] Verify automatic abort, rollback command, on-call owner, and post-promotion observation.
- [ ] Verify signed SBOM/provenance and deployed digest admission.
- [ ] Verify backup freshness, restore drill, evidence-bundle recovery, retention, and deletion receipts.
- [ ] Sign a final residual-risk register and governance certificate based on evidence artifacts, not the blanket claim that all prior tracks are complete.

## Final decision

**Approve the new Track P and reject the current Track D sequencing.** Retain the existing 4.D product intent, especially the Trace Inspector provenance wedge, but split each milestone into contract, capability, assurance, and release-readiness work. Treat the static site, current CRUD routers, permission constants, aggregate trace rows, TTLs, planned deployment prose, and existing smoke tests as foundations or evidence inputs—not as proof that the operator product exists. The first credible delivery is a narrow, authenticated, tenant-safe, metadata-first Explore and Trace Inspector slice built on Track P.

## References

[1]: https://nextjs.org/docs/app/guides/static-exports "Next.js: How to create a static export"
[2]: https://html.spec.whatwg.org/multipage/server-sent-events.html "WHATWG HTML: Server-sent events"
[3]: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html "OWASP Session Management Cheat Sheet"
[4]: https://fastapi.tiangolo.com/advanced/generate-clients/ "FastAPI: Generating SDKs"
[5]: https://playwright.dev/docs/ci-intro "Playwright: Setting up CI"
[6]: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02016R0679-20160504 "GDPR Article 17: Right to erasure"
[7]: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/ "OpenTelemetry GenAI semantic conventions"
[8]: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html "OWASP Multi-Tenant Application Security Cheat Sheet"
[9]: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html "OWASP Authorization Cheat Sheet"
[10]: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html "AWS Prescriptive Guidance: Transactional outbox pattern"
[11]: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md "CloudEvents Specification"
[12]: https://owasp.org/www-project-top-10-for-large-language-model-applications/ "OWASP Top 10 for Large Language Model Applications"
[13]: https://owasp.org/Top10/2021/A09_2021-Security_Logging_and_Monitoring_Failures/ "OWASP A09: Security Logging and Monitoring Failures"
[14]: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf "NIST AI 600-1 Generative AI Profile"
[15]: https://docs.datadoghq.com/tracing/trace_explorer/query_syntax/ "Datadog Trace Explorer query syntax"
[16]: https://clickhouse.com/docs/concepts/best-practices/choosing-a-primary-key "ClickHouse: Choosing a primary key"
[17]: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/ "Kubernetes: Configure liveness, readiness and startup probes"
[18]: https://www.postgresql.org/docs/current/continuous-archiving.html "PostgreSQL: Continuous archiving and point-in-time recovery"
[19]: https://slsa.dev/spec/v1.2/build-provenance "SLSA Build Provenance v1.2"
[20]: https://www.w3.org/TR/trace-context/ "W3C Trace Context Recommendation"
[21]: https://opentelemetry.io/docs/specs/otel/logs/ "OpenTelemetry Logging Specification"