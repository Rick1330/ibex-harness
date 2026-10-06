# Gap Register

**Status:** `specified`; update with every architecture or milestone change.

| ID | Priority | Gap | Impact | Required disposition |
|---|---:|---|---|---|
| GAP-001 | P0 | Shipped/local/provisional/design claims conflict across docs. | False production expectations. | Initial packet in issue #935 / ADR-0084; expanded audit and recommendation packet in issue #939. Named-owner/profile/evidence decision and G0 acceptance remain pending; closure of #935 via PR #936 is not acceptance. |
| GAP-002 | P0 | Authority matrix for auth, policy, budget, Redis, evidence is incomplete. | Incorrect fail-open behavior. | Freeze principal/policy/evidence authority and Redis/ClickHouse projection limits through the issue #939 decision packet; named-owner decision pending. |
| GAP-003 | P0 | No complete route/proto/event/MCP contract registry. | Unreviewable compatibility drift. | Proposed principal, run, idempotency, evidence, and relay rows remain subject to G0 owner review; issue #939 contains the full cross-area audit; runtime/MCP expansion is not authorized yet. |
| GAP-004 | P0 | 20/40/45/50/100 ms claims conflict and are unmeasured. | Impossible SLO ownership. | Ratify one budget and publish benchmarks. |
| GAP-005 | P0 | Tenant isolation/deletion/evidence coverage is not end-to-end proven. | Catastrophic confidentiality/integrity risk. | Principal propagation and evidence tenant/replay work require G0 contract approval first. PR #936 contains only partial relay payload-digest/ack-loss hardening; deletion and full-store coverage remain open. |
| GAP-006 | P0 | Atomic reservation/idempotency/reconciliation is not accepted. | Billing/cost integrity risk. | Define durable ledger and failure semantics. |
| GAP-007 | P1 | Generic memory record lacks typed lifecycle/provenance/checkpoints. | Poisoning, stale context, irreproducible behavior. | Accept typed memory/context contract. PR #936 adds a bounded `valid_from`/`valid_until` read fence across vector, FTS, final hydration, and hot-cache paths, with a separate historical conflict-candidate mode; typed lifecycle/provenance/checkpoints remain open. |
| GAP-008 | P1 | Provider alias/capability/streaming/usage semantics are fragmented. | Silent semantic loss and unsafe fallback. | Capability manifest and conformance matrix. |
| GAP-009 | P1 | MCP/operator boundaries and audit status are mixed. | Privilege and support confusion. | Read-only-first contract and operator API boundary. PR #936 makes Redis rate limiting fail closed in protected profiles and records `rate_limit_unavailable`; audit durability and operator boundary remain open. |
| GAP-010 | P1 | DecisionService/model registry/calibration/benchmark do not exist. | Model overreach and unmeasured latency. | Keep design-intent; gate at G10. |
| GAP-011 | P1 | Backup/restore/migration/incident/operator evidence is incomplete. | Unrecoverable production state. | Select any relay/sink recovery pilot only after G0 and evidence identity/redaction acceptance; hosted/HA certification remains open. PR #936 adds local PostgreSQL digest-mismatch rejection and ack-loss replay evidence; this does not certify recovery. |
| GAP-012 | P2 | Graph/A2A/marketplace/sandbox/broad provider expansion is premature. | Scope and dependency explosion. | Keep deferred until core gates pass. |

Every gap needs an owner, source references, decision date, dependency, evidence artifact, and disposition. Closing prose is not closing evidence.

## Eight-area audit crosswalk

The research labels below are not replacements for canonical GAP IDs. Several areas overlap, so implementation must follow the single-owner work packages and dependency graph in the [pre-G0 synthesis](20-pre-g0-gap-synthesis-and-workplan.md), not create duplicate projects per audit label. Candidate defaults and missing owner/evidence fields are captured in the [proposal-only G0 decision worksheet](21-g0-owner-decision-recommendations.md); it does not authorize implementation.

| Audit cluster | Canonical GAP IDs | Source-linked evidence |
|---|---|---|
| Identity/principal | GAP-001, GAP-002, GAP-003, GAP-005 | [GAP-01](../research/ibex-preflight-2026-10/gap-01-identity-principal-verified.md) |
| Budget admission | GAP-002, GAP-003, GAP-006 | [GAP-02](../research/ibex-preflight-2026-10/gap-02-budget-admission-verified.md) |
| Provider compatibility | GAP-003, GAP-004, GAP-008 | [GAP-03](../research/ibex-preflight-2026-10/gap-03-provider-compat-verified.md) |
| Memory lifecycle | GAP-005, GAP-007, GAP-011 | [GAP-04](../research/ibex-preflight-2026-10/gap-04-memory-lifecycle-verified.md) |
| Context compiler | GAP-004, GAP-005, GAP-007 | [GAP-05](../research/ibex-preflight-2026-10/gap-05-context-compiler-verified.md) |
| MCP governance | GAP-003, GAP-005, GAP-009 | [GAP-06](../research/ibex-preflight-2026-10/gap-06-mcp-governance-verified.md) |
| Evidence/recovery | GAP-003, GAP-005, GAP-011 | [GAP-07](../research/ibex-preflight-2026-10/gap-07-evidence-recovery-verified.md) |
| Skills/approvals/control plane | GAP-001, GAP-002, GAP-003, GAP-005, GAP-006, GAP-009, GAP-011 | [GAP-08](../research/ibex-preflight-2026-10/gap-08-control-plane-verified.md) |

These reports are independent audit inputs; the workplan records provenance and which repository governance claims the main agent verified. Reported component tests do not imply profile acceptance. G0 remains `UNKNOWN / NOT ACCEPTED` until the canonical ledger contains the required dated owner decision.

## Production-readiness scope update

On 2026-10-06, the task owner superseded the earlier local-only task limit and selected a provider-neutral Kubernetes/Helm application-preparation profile with external data-plane interfaces; provider-specific IaC is deferred, deployment is prohibited, and no HA/support claim is made until evidence exists. Development Compose remains local-only. The selection is not a supported production profile or G0 acceptance; actual topology, external data-plane implementations, and G0 remain unresolved. The five-area audit is recorded in the [production-readiness audit and no-deploy workplan](22-production-readiness-no-deploy-plan.md). Its findings primarily reinforce GAP-001 (status/profile claims), GAP-005 (security/isolation evidence), and GAP-011 (recovery/operator evidence) and the open 4.P.5 milestone; they do not create new canonical GAP IDs or close any existing gap.

## Issue #935 historical disposition and issue #939 preparation

| Cluster | Proposed owner | Decision date | Dependency | Evidence artifact | Disposition |
|---|---|---|---|---|---|
| G0 / GAP-001–003 | Architecture + Auth/Proxy | Pending owner review | ADR-0084, contract registry, profile matrix | Initial packet in issue #935; expanded docs-only audit packet in issue #939 and this commit | Prepared for review; not accepted. Issue #935 closure via PR #936 is not G0 acceptance |
| GAP-005 principal seam | Auth/Proxy + Context | Pending G0 | Verified PrincipalContext and transport trust mapping | Planned zero-downstream-call and cross-tenant matrix | Bounded post-G0 slice only |
| GAP-005/GAP-011 evidence | Evidence/Security + Platform | Pending G0 | Evidence identity, redaction, acknowledgement, relay/sink authority | Planned replay/redaction/ack-loss/recovery bundle | Bounded post-G0 slice only |
| GAP-007 temporal read fence | Memory + Context | Pending owner review | Existing temporal schema and read-path contract | PR #936 focused request-mode and SQL predicate regression tests; hosted expiry evidence pending | Bounded fix merged; gap remains partial/open |
| GAP-009 protected limiter | MCP + Security | Pending owner review | Protected profile requires Redis; typed dependency failure | PR #936 focused config/limiter/invocation tests | Bounded fail-closed behavior merged; audit/operator gap remains open |

## Follow-ups

### Finding — GAP-005/GAP-011 relay payload integrity and acknowledgement-loss evidence

- **Reproducible steps:** Construct or retrieve an outbox row whose `payload_digest` is a well-formed 64-character hexadecimal string for different bytes; or deliver a claimed row successfully and lose the `mark_delivered` acknowledgement before replaying it.
- **Expected:** The relay rejects the tampered row before invoking the sink; after acknowledgement loss, replay may invoke the sink again but stable `(event_id, aggregate_seq)` identity produces one externally applied effect.
- **Actual before PR #936:** Validation checked only digest shape, and the integration test did not exercise deliver-success/ack-loss/recovery timing.
- **Source:** `packages/evidenceoutbox/relay.go`, `packages/evidenceoutbox/relay_unit_test.go`, `packages/evidenceoutbox/store_integration_test.go`; merged implementation is PR #936, commit `125fde3da214649f319cb54e5f87b96f2ed3575c`.
- **Impact / severity:** Evidence integrity and recovery accounting risk; **P1** for protected evidence profiles.
- **Profile:** PostgreSQL evidence/outbox relay; local integration profile only. Hosted/HA profiles are not certified.
- **Evidence:** Digest mismatch rejection, uppercase digest acceptance, unit-level idempotent replay, and PostgreSQL integration ack-loss/replay test when the integration database is available.
- **Owner:** Evidence/Security + Platform; **reviewer:** architecture owner remains to be named in the formal G0 acceptance packet; issue #939 tracks documentation preparation only.
- **Due / next action:** Before any evidence claim is promoted, add profile-specific sink deduplication, tombstone replay fencing, redaction rejection, and hosted recovery evidence.
- **Status:** Digest mismatch rejection and PostgreSQL ack-loss/replay hardening are merged and locally evidenced. This is partial; GAP-005/GAP-011 remain open and non-accepted because required-before-ack semantics, a deployed sink, redaction, tombstone fencing, and hosted recovery are not proven.

### Finding — GAP-007 temporal retrieval fence can suppress historical conflict candidates

- **Reproducible steps:** Seed an `active` memory with a closed validity interval, persist its embedding, then write a newer same-subject memory through the HTTP path. Run the Phase 3 memory E2E supersede check.
- **Expected:** Historical active memory is available to the conflict classifier so a newer non-overlapping claim can supersede it; ordinary user retrieval still excludes expired intervals.
- **Actual before PR #936:** The shared vector-search query applied the current-time validity fence before write-path near-duplicate detection, so the expired candidate was omitted and remained `active`; CI reported `supersede-check: old memory status='active', want superseded`.
- **Source:** `services/memory/app/vectorstore/pgvector_store.py`, `services/memory/app/dedup/service.py`, `services/memory/app/conflict/persist.py`, `infra/scripts/verify_phase3_memory_e2e.sh`, remote CI job `e2e-smoke-p3-memory`; the original finding was recorded at `c2034bc`, and PR #936 (`125fde3da214649f319cb54e5f87b96f2ed3575c`) added explicit historical-candidate inclusion for conflict evaluation while preserving ordinary read fences.
- **Impact / severity:** Stale/conflicting memory lifecycle and CI correctness risk; **P1** for memory write semantics.
- **Profile:** Memory HTTP write path with PostgreSQL/pgvector; local unit coverage exists, hosted integration evidence pending.
- **Evidence:** PR #936 adds request-mode and SQL-contract regression tests for expired conflict candidates; the audit did not establish a current hosted Phase 3 E2E result, and no user-read path should be weakened.
- **Owner:** Memory + Context; **reviewer:** architecture owner remains to be named in the formal G0 acceptance packet; issue #939 tracks documentation preparation only.
- **Due / next action:** Re-run the hosted Phase 3 memory E2E and add profile-level temporal/deletion/recovery evidence; preserve default user retrieval fencing and verify all call sites keep `include_expired` restricted to conflict classification.
- **Status:** The scoped temporal-fence regression is fixed in merged code; GAP-007 remains partial/open because typed lifecycle, deletion, tombstones, provenance, and hosted/profile acceptance are not complete.

The pending entries are deliberately not `shipped-accepted`. A future acceptance update must replace `Pending owner review` with named owners and dates, link the evidence artifact, and record limitations and review expiry.
