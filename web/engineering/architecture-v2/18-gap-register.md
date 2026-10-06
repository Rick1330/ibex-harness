# Gap Register

**Status:** `specified`; update with every architecture or milestone change.

| ID | Priority | Gap | Impact | Required disposition |
|---|---:|---|---|---|
| GAP-001 | P0 | Shipped/local/provisional/design claims conflict across docs. | False production expectations. | Issue #935 / ADR-0084: prepare the G0 ledger packet with owner, profile, evidence, limitations, and review date; acceptance pending. |
| GAP-002 | P0 | Authority matrix for auth, policy, budget, Redis, evidence is incomplete. | Incorrect fail-open behavior. | Issue #935 / ADR-0084: freeze principal/policy/evidence authority and Redis/ClickHouse projection limits; named-owner decision pending. |
| GAP-003 | P0 | No complete route/proto/event/MCP contract registry. | Unreviewable compatibility drift. | Issue #935: complete proposed principal, run, idempotency, evidence, and relay rows; MCP/runtime expansion remains deferred. |
| GAP-004 | P0 | 20/40/45/50/100 ms claims conflict and are unmeasured. | Impossible SLO ownership. | Ratify one budget and publish benchmarks. |
| GAP-005 | P0 | Tenant isolation/deletion/evidence coverage is not end-to-end proven. | Catastrophic confidentiality/integrity risk. | Issue #935 selects only a bounded proxy→context principal seam and evidence tenant/replay matrix; deletion and full-store coverage remain open. |
| GAP-006 | P0 | Atomic reservation/idempotency/reconciliation is not accepted. | Billing/cost integrity risk. | Define durable ledger and failure semantics. |
| GAP-007 | P1 | Generic memory record lacks typed lifecycle/provenance/checkpoints. | Poisoning, stale context, irreproducible behavior. | Accept typed memory/context contract. |
| GAP-008 | P1 | Provider alias/capability/streaming/usage semantics are fragmented. | Silent semantic loss and unsafe fallback. | Capability manifest and conformance matrix. |
| GAP-009 | P1 | MCP/operator boundaries and audit status are mixed. | Privilege and support confusion. | Read-only-first contract and operator API boundary. |
| GAP-010 | P1 | DecisionService/model registry/calibration/benchmark do not exist. | Model overreach and unmeasured latency. | Keep design-intent; gate at G10. |
| GAP-011 | P1 | Backup/restore/migration/incident/operator evidence is incomplete. | Unrecoverable production state. | Issue #935 selects one relay/sink recovery pilot after G0 and evidence identity/redaction acceptance; hosted/HA certification remains open. |
| GAP-012 | P2 | Graph/A2A/marketplace/sandbox/broad provider expansion is premature. | Scope and dependency explosion. | Keep deferred until core gates pass. |

Every gap needs an owner, source references, decision date, dependency, evidence artifact, and disposition. Closing prose is not closing evidence.

## Issue #935 disposition record

| Cluster | Proposed owner | Decision date | Dependency | Evidence artifact | Disposition |
|---|---|---|---|---|---|
| G0 / GAP-001–003 | Architecture + Auth/Proxy | Pending owner review | ADR-0084, contract registry, profile matrix | Proposed packet in issue #935 and this commit | Documentation packet prepared; not accepted |
| GAP-005 principal seam | Auth/Proxy + Context | Pending G0 | Verified PrincipalContext and transport trust mapping | Planned zero-downstream-call and cross-tenant matrix | Bounded post-G0 slice only |
| GAP-005/GAP-011 evidence | Evidence/Security + Platform | Pending G0 | Evidence identity, redaction, acknowledgement, relay/sink authority | Planned replay/redaction/ack-loss/recovery bundle | Bounded post-G0 slice only |

The pending entries are deliberately not `shipped-accepted`. A future acceptance update must replace `Pending owner review` with named owners and dates, link the evidence artifact, and record limitations and review expiry.
