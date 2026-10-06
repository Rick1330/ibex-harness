# Gap Register

**Status:** `specified`; update with every architecture or milestone change.

| ID | Priority | Gap | Impact | Required disposition |
|---|---:|---|---|---|
| GAP-001 | P0 | Shipped/local/provisional/design claims conflict across docs. | False production expectations. | Issue #935 / ADR-0084: prepare the G0 ledger packet with owner, profile, evidence, limitations, and review date; acceptance pending. |
| GAP-002 | P0 | Authority matrix for auth, policy, budget, Redis, evidence is incomplete. | Incorrect fail-open behavior. | Issue #935 / ADR-0084: freeze principal/policy/evidence authority and Redis/ClickHouse projection limits; named-owner decision pending. |
| GAP-003 | P0 | No complete route/proto/event/MCP contract registry. | Unreviewable compatibility drift. | Issue #935: complete proposed principal, run, idempotency, evidence, and relay rows; MCP/runtime expansion remains deferred. |
| GAP-004 | P0 | 20/40/45/50/100 ms claims conflict and are unmeasured. | Impossible SLO ownership. | Ratify one budget and publish benchmarks. |
| GAP-005 | P0 | Tenant isolation/deletion/evidence coverage is not end-to-end proven. | Catastrophic confidentiality/integrity risk. | Issue #935 selects only a bounded proxy→context principal seam and evidence tenant/replay matrix; deletion and full-store coverage remain open. Relay payload-digest validation and ack-loss replay evidence are partial hardening only. |
| GAP-006 | P0 | Atomic reservation/idempotency/reconciliation is not accepted. | Billing/cost integrity risk. | Define durable ledger and failure semantics. |
| GAP-007 | P1 | Generic memory record lacks typed lifecycle/provenance/checkpoints. | Poisoning, stale context, irreproducible behavior. | Accept typed memory/context contract. Draft tranche adds a bounded read fence for `valid_from`/`valid_until` across vector, FTS, final hydration, and hot-cache paths; typed lifecycle/provenance/checkpoints remain open. |
| GAP-008 | P1 | Provider alias/capability/streaming/usage semantics are fragmented. | Silent semantic loss and unsafe fallback. | Capability manifest and conformance matrix. |
| GAP-009 | P1 | MCP/operator boundaries and audit status are mixed. | Privilege and support confusion. | Read-only-first contract and operator API boundary. Draft tranche makes Redis rate limiting fail closed in staging/production and records `rate_limit_unavailable`; audit durability and operator boundary remain open. |
| GAP-010 | P1 | DecisionService/model registry/calibration/benchmark do not exist. | Model overreach and unmeasured latency. | Keep design-intent; gate at G10. |
| GAP-011 | P1 | Backup/restore/migration/incident/operator evidence is incomplete. | Unrecoverable production state. | Issue #935 selects one relay/sink recovery pilot after G0 and evidence identity/redaction acceptance; hosted/HA certification remains open. Existing PostgreSQL relay now has digest-mismatch rejection and deterministic ack-loss replay evidence; recovery certification remains open. |
| GAP-012 | P2 | Graph/A2A/marketplace/sandbox/broad provider expansion is premature. | Scope and dependency explosion. | Keep deferred until core gates pass. |

Every gap needs an owner, source references, decision date, dependency, evidence artifact, and disposition. Closing prose is not closing evidence.

## Issue #935 disposition record

| Cluster | Proposed owner | Decision date | Dependency | Evidence artifact | Disposition |
|---|---|---|---|---|---|
| G0 / GAP-001–003 | Architecture + Auth/Proxy | Pending owner review | ADR-0084, contract registry, profile matrix | Proposed packet in issue #935 and this commit | Documentation packet prepared; not accepted |
| GAP-005 principal seam | Auth/Proxy + Context | Pending G0 | Verified PrincipalContext and transport trust mapping | Planned zero-downstream-call and cross-tenant matrix | Bounded post-G0 slice only |
| GAP-005/GAP-011 evidence | Evidence/Security + Platform | Pending G0 | Evidence identity, redaction, acknowledgement, relay/sink authority | Planned replay/redaction/ack-loss/recovery bundle | Bounded post-G0 slice only |
| GAP-007 temporal read fence | Memory + Context | Pending owner review | Existing temporal schema and read-path contract | Focused SQL predicate tests; integration expiry evidence pending | Partial hardening landed in draft; gap remains open |
| GAP-009 protected limiter | MCP + Security | Pending owner review | Protected profile requires Redis; typed dependency failure | Focused config/limiter/invocation tests | Partial hardening landed in draft; audit/operator gap remains open |

## Follow-ups

### Finding — GAP-005/GAP-011 relay payload integrity and acknowledgement-loss evidence

- **Reproducible steps:** Construct or retrieve an outbox row whose `payload_digest` is a well-formed 64-character hexadecimal string for different bytes; or deliver a claimed row successfully and lose the `mark_delivered` acknowledgement before replaying it.
- **Expected:** The relay rejects the tampered row before invoking the sink; after acknowledgement loss, replay may invoke the sink again but stable `(event_id, aggregate_seq)` identity produces one externally applied effect.
- **Actual before this tranche:** Validation checked only digest shape, and the integration test explicitly did not exercise deliver-success/ack-loss/recovery timing.
- **Source:** `packages/evidenceoutbox/relay.go`, `packages/evidenceoutbox/relay_unit_test.go`, `packages/evidenceoutbox/store_integration_test.go`, commit `1971d9c` plus the follow-up commit on this branch.
- **Impact / severity:** Evidence integrity and recovery accounting risk; **P1** for protected evidence profiles.
- **Profile:** PostgreSQL evidence/outbox relay; local integration profile only. Hosted/HA profiles are not certified.
- **Evidence:** Digest mismatch rejection, uppercase digest acceptance, unit-level idempotent replay, and PostgreSQL integration ack-loss/replay test when the integration database is available.
- **Owner:** Evidence/Security + Platform; **reviewer:** architecture owner to be named in issue #935.
- **Due / next action:** Before any evidence claim is promoted, add profile-specific sink deduplication, tombstone replay fencing, redaction rejection, and hosted recovery evidence.
- **Status:** Partial hardening implemented; GAP-005 and GAP-011 remain open and non-accepted.

### Finding — GAP-007 temporal retrieval fence can suppress historical conflict candidates

- **Reproducible steps:** Seed an `active` memory with a closed validity interval, persist its embedding, then write a newer same-subject memory through the HTTP path. Run the Phase 3 memory E2E supersede check.
- **Expected:** Historical active memory is available to the conflict classifier so a newer non-overlapping claim can supersede it; ordinary user retrieval still excludes expired intervals.
- **Actual:** The shared vector search query applies the current-time validity fence before write-path near-duplicate detection, so the expired candidate is omitted and remains `active`; CI reports `supersede-check: old memory status='active', want superseded`.
- **Source:** `services/memory/app/vectorstore/pgvector_store.py`, `services/memory/app/dedup/service.py`, `services/memory/app/conflict/persist.py`, `infra/scripts/verify_phase3_memory_e2e.sh`, remote CI job `e2e-smoke-p3-memory`; current branch commit `c2034bc`.
- **Impact / severity:** Stale/conflicting memory lifecycle and CI correctness risk; **P1** for memory write semantics.
- **Profile:** Memory HTTP write path with PostgreSQL/pgvector; local unit coverage exists, hosted integration evidence pending.
- **Evidence:** Existing E2E failure plus integration tests that expect supersession; no user-read path should be weakened.
- **Owner:** Memory + Context; **reviewer:** architecture owner to be named in issue #935.
- **Due / next action:** Add an explicit non-user-retrieval search mode for historical conflict candidates, preserve the default temporal fence, and add focused SQL/request regression tests before rerunning the E2E.
- **Status:** Finding verified; fix in progress as a scoped GAP-007 hardening slice.

The pending entries are deliberately not `shipped-accepted`. A future acceptance update must replace `Pending owner review` with named owners and dates, link the evidence artifact, and record limitations and review expiry.
