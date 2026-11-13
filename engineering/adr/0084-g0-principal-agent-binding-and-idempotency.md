---
title: "G0 principal, agent binding, and idempotency contract"
description: "G0 contract packet for verified principal propagation, token-bound agent authorization, and tenant-scoped replay semantics. The five contract shapes were accepted on 2026-10-10; runtime seams remain provisional."
---

::decision-banner{status="Accepted" date="2026-10-05" id="0084"}
::

# ADR-0084: G0 principal, agent binding, and idempotency contract

- **Status:** Accepted for the five contract shapes on 2026-10-10 (contract text and safety semantics only; review/expiry moved to 2027-02-06 by the 2026-11-06 review, and `idempotency-operation.v1` was renewed to the same date on 2026-11-11). Runtime seams remain `provisional`: no runtime G1-G4 exit, hosted/HA certification, or production-readiness claim follows from this acceptance. Original issue [#935](https://github.com/Rick1330/ibex-harness/issues/935) is closed and historical; [issue #944](https://github.com/Rick1330/ibex-harness/issues/944) was closed by [PR #943](https://github.com/Rick1330/ibex-harness/pull/943), squash-merged 2026-10-09 at commit `1934456`, then reopened on 2026-10-09 solely for a docs-only cleanup.
- **Date:** 2026-10-05
- **Owners:** Auth/Proxy, Context, Architecture/Proxy, Platform/Data, Evidence/Platform, Security/Privacy, and Evidence/Operations roles; Rick1330 (acting) was provisionally confirmed by the owner on 2026-10-09; actual individual role assignments remain pending by/within 2026-10-22.
- **Scope:** G0/G1/G2 foundation and the evidence contract required before the first bounded runtime seams
- **Supersedes:** none; extends the specified contracts in architecture-v2

## Context

IBEX already validates bearer tokens, derives an organization and permission bitmap, verifies requested agent ownership/status, and carries request/session identifiers through several local paths. These local slices do not by themselves implement the cross-boundary principal/run contract accepted here; the accepted text is the contract, and the runtime seams below are what remains to be built and evidenced. In particular, the token validation response marks `agent_id` as an agent-scoped token field, but the selected agent must be checked against that binding before any agent-specific work is authorized.

The architecture-v2 roadmap made G0 a hard documentation and contract freeze. New database lifecycles, service/package boundaries, budget enforcement changes, provider adapters, and write-capable effects were blocked until the freeze was accepted; the shape acceptance on 2026-10-10 released the freeze for contract text only. This ADR is therefore a contract and implementation anchor, not a claim that any runtime seam or G1-G4 exit has passed.

## Decision

### 0. Review state and decision boundary

This document is the **G0 contract packet** originally tracked by issue #935 (now closed; historical context). The implementation follow-up issue #944 was closed by PR #943, squash-merged on 2026-10-09, and reopened on 2026-10-09 solely for a docs-only cleanup. The packet's five contract shapes were **accepted on 2026-10-10** by Rick1330 acting across the owner roles, and the acceptance is recorded in the status ledger and in the contract registry ([`03-contract-registry.md`](../architecture-v2/03-contract-registry.md)). Acceptance freezes contract text and safety semantics only: it does not approve a runtime seam, and a merge, green local test, or author statement does not imply G0 exit. Rick1330 remains the acting owner across the listed roles; no independent reviewer is named. Each runtime seam below still needs its own owner/status-ledger decision and its G1/G2/G4 evidence gate before it is implementation-ready.

The first post-G0 candidate implementation boundary is deliberately narrow, but each seam remains subject to a separate owner/status-ledger decision and its applicable G1/G2/G4 evidence gate:

1. one additive, authenticated proxy-to-context `PrincipalContext v1` mapping;
2. one operation-specific evidence persistence/idempotency/redaction slice; and
3. one operational evidence relay with one tenant-filtered idempotent sink and recovery evidence.

No item in this ADR authorizes a durable `RunEnvelope`, atomic budget reservation, provider manifest, typed memory lifecycle, MCP governance change, control-plane executor, or other new side-effect boundary.

### 0.1 Bounded safety hardening carried by the draft

To accelerate the highest-value risk reduction without creating a new authority boundary, the draft implementation also carries four partial hardening slices:

- Memory vector, full-text, final-hydration, and hot-cache reads enforce the existing half-open `[valid_from, valid_until)` interval in addition to active-status and tombstone predicates.
- The write path uses an explicit `HISTORICAL_CONFLICT_CANDIDATES` mode for near-duplicate and supersession candidate evaluation; the direct candidate loader rejects `USER_RETRIEVAL`, while user retrieval retains the current-validity fence.
- MCP staging/production configuration requires Redis for the org limiter; Redis failures raise a typed `rate_limit_unavailable` result instead of admitting a protected-profile tool call. Development retains the explicit no-Redis exception.
- Evidence relay rows carry a producer-declared redaction class and optional tombstone fence as additive JSON fields; the relay fails closed on unsafe classes, missing fences, or sinks without the typed fence-aware hook. This does not add a sanitizer, production sink, or lifecycle-table integration.

These changes are local safety fences, backed by focused tests. They do not close typed memory provenance/checkpoints, MCP audit durability/operator boundaries, or the broader G0/G1/G2/G4 acceptance gates; the status ledger records them as partial dispositions.

### 1. Verified principal authority

- `org_id`, subject identity, token scope, permissions, and resource ownership are derived from AuthService and policy evaluation.
- Caller-provided organization, agent, project, session, run, or resource identifiers are selectors only; they never grant authority.
- A logical run is correlation and lineage only. It is not a permission grant.
- Missing, stale, forged, mismatched, or unavailable identity/policy state denies or returns a typed dependency failure before provider, context, tool, or mutation work.

### 2. Token-bound agent selection

- When a validated bearer token contains `agent_id`, the request-selected agent must equal that identifier.
- A mismatch is an existence-safe authorization denial and must not trigger target-agent lookup or downstream work.
- Organization-scoped tokens without `agent_id` may select an active agent only after the existing organization ownership/status checks succeed.
- Any future cross-agent grant must be separately authenticated, explicit, resource-scoped, expiring, auditable, and approved through a subsequent ADR. It is not implied by this contract.
- AuthService enforces the rule authoritatively; the proxy enforces it as defense in depth before calling the agent verifier.

### 3. Protected router readiness

- Staging and production protected routes must not be mounted when `Validator` is present but `AgentVerifier` is absent.
- Development and test profiles may use explicit fakes or controlled exceptions, but those exceptions must remain visible in test wiring and must not be inherited by protected deployment profiles.
- A missing verifier is a readiness/configuration failure, not an empty authorization result.

### 4. Initial idempotency and replay contract

This ADR freezes the semantics for the first implementation slice; it does not add a new persistence boundary.

- Idempotency keys are tenant-bound and scoped to an operation/resource class.
- The server stores or derives a canonical request body hash before accepting a mutation.
- Adopt RFC 8785 JSON Canonicalization Scheme (JCS), versioned as `jcs/v1`, for the canonical body bytes. Go and Python conformance vectors must cover duplicate keys, Unicode, numeric-domain limits, and absent/default fields.
- Same tenant + same operation scope + same key + same body hash returns or resumes the existing operation.
- Same key with a different body hash returns a stable conflict and never executes a second effect.
- Cross-tenant key reuse is isolated.
- Ambiguous completion is resolved by operation ID lookup and reconciliation, never by blind retry.
- Retry attempts belong to one logical run but receive distinct attempt identity.
- TTL, retention, crash recovery, cancellation, and deletion behavior must be specified per operation before a durable migration is accepted.

### 5. Evidence acknowledgement and redaction boundary

- PostgreSQL evidence/outbox persistence is the canonical authority for the selected profile. Redis, ClickHouse, object storage, queues, and telemetry exports are not authorization or acknowledgement authorities.
- Every evidence mutation has a stable operation scope, tenant-bound idempotency key, canonical body hash, operation ID, event ID, aggregate sequence/version, schema version, and payload digest. A same-body retry returns or reconciles the existing identifiers; a body conflict never performs a second effect.
- Mapping A: return ordinary success only after canonical evidence/outbox durability; if required evidence fails or commit status is unknown, do not report success and reconcile by operation ID. Mapping B: only when the selected profile explicitly permits degradation, return a typed, machine-readable `uncertified` outcome with durable retry/reconciliation state. Silent log-and-continue is forbidden. Exact HTTP status/error mapping still requires owner approval; the current detached log-only call remains an implementation gap.
- Producers declare `unclassified`, `metadata`, or `prohibited` only after sanitization; absent classification remains `unclassified`, never implicitly `metadata`. The relay rejects unclassified, prohibited, and unsupported values before delivery. This checks the declared class, not payload contents; producer-side sanitizer/validator evidence is still required. Bearer/API tokens, credentials, prompts, memory bodies, embeddings, and unredacted PII remain forbidden in ordinary event payloads, logs, and outbox rows.
- Select ClickHouse as the v1 projection sink, but keep its adapter G4-gated. Deduplicate `(org_id, event_id, aggregate_seq)` under a tenant predicate. Platform/Data owns the authoritative PostgreSQL resource-lifecycle table; the future sink check must be atomic with projection write and fail closed. No adapter or lifecycle-table integration is implemented in this round.

On 2026-10-08 the unit suite verified digest integrity, ack-loss replay, rejected unsafe classes, missing fences, and missing fence-aware hooks; all seven PostgreSQL evidenceoutbox integration tests passed against the disposable local Podman test DB. A new database-backed regression confirms that an unsafe row is durably marked poison through the real failure helper; the relay now supplies a positive delay required by that helper even though poison rows are terminal. The current production session producer (`services/proxy/internal/http/session/evidence.go:91-118`) supplies neither class nor fence, so its rows default to unclassified/fenceless and are intentionally poisoned if sent to the relay until a safe producer update exists. This remains partial evidence: there is no ClickHouse adapter, authoritative lifecycle-table integration, producer content sanitizer/class proof, hosted recovery, or G0 acceptance. The additive Go/JSON fields required no database migration.

The memory write path uses `HISTORICAL_CONFLICT_CANDIDATES` for write-time near-duplicate/supersession evaluation in `dedup/service.py` and requires that mode in the `CandidateLoad` guard in `conflict/persist.py`; the current user-read repository explicitly selects `USER_RETRIEVAL` and preserves the half-open current-validity fence (`services/memory/app/vectorstore/base.py`, `pgvector_store.py`, `dedup/service.py`, `conflict/persist.py`, `read/repository.py`). `SearchMode` is an internal call-site control, not a capability token: the current user-facing repository does not expose historical mode, but a direct in-process vector-store caller can select it; keep that API internal and audit new call sites. Candidate loading and supersession persistence are org-scoped but lack a direct `agent_id` predicate, relying on the current agent-scoped upstream search; add direct cross-agent negative coverage before broadening that API. `InMemoryVectorStore` has no validity timestamps and ignores mode, so its unit tests cannot establish temporal-mode parity. On 2026-10-08, the full memory unit suite passed (481 passed, 88 deselected; 97.62% coverage), four PostgreSQL-backed integration modules passed (23 tests), and the Phase 3 HTTP lifecycle E2E completed successfully against local Podman PostgreSQL/Redis, including user-read fence, supersession, status/link, and teardown. The E2E explicitly skipped only the deferred org-scope GDPR/MinIO purge item (#641); the #647 stale-cache behavior remains a separate known gap. GAP-007 remains open for typed lifecycle/provenance/checkpoints and owner review; these tests do not certify production isolation or close G0.

### 6. Authority, trust, and profile matrix

| Contract area | Authority | Trusted input | Failure behavior | First bounded seam |
|---|---|---|---|---|
| Verified principal | AuthService/enforcement plane | Authenticated token validation and policy result | Deny or typed dependency failure; no downstream work | Proxy to context |
| Policy snapshot | Auth/enforcement plane with AuthService-issued immutable snapshot recommended; identity/window await owner confirmation | Verified server-side ID, digest, effective epoch, and freshness | Deny/503 when missing, stale, or contradictory | Carry linkage only |
| Run lineage | Enforcement plane | Server-minted run/attempt identifiers | Correlation only; never grants permission | No durable RunEnvelope |
| Evidence lifecycle | PostgreSQL evidence/outbox authority | Validated, redacted event envelope | Atomic failure or explicit uncertified outcome | PersistRun and relay |
| Projection/sink | ClickHouse selected for v1 (adapter G4-gated); PostgreSQL resource-lifecycle table authoritative | Relay-validated event envelope and explicit org-scoped fence | Fail closed; retry/poison, no stale/tombstoned projection | No adapter or lifecycle-table integration in this round |

The accepted profile, owners, dependency assumptions, trust labels, compatibility class, and review/expiry date must be recorded in the architecture-v2 status ledger. Unknown or unavailable authority is not equivalent to an empty result.

## Failure and privacy semantics

- Identity/policy mismatch: stable existence-safe authorization denial.
- Auth/policy dependency outage: typed service-unavailable/degraded response; no security fallback.
- Missing protected-profile verifier: router construction/readiness failure.
- Idempotency body mismatch: conflict; no downstream side effect.
- Logs and evidence contain identifiers and outcomes only; never bearer tokens, raw memory, prompts, secrets, or unredacted sensitive content.

## Compatibility and rollout

The agent-binding enforcement is backward-compatible for organization-scoped tokens. Existing agent-scoped tokens continue to work only for their bound agent. The router readiness check applies only to staging and production profiles. Any future protobuf or durable idempotency schema change must be additive, generated, migration-safe, and covered by mixed-version tests.

Rollout order:

1. Review and accept the G0 contract packet, recording the decision in the status ledger.
2. Separately approve and implement the proxy-to-context seam and evidence persistence contract as reviewable changes.
3. Separately approve and wire one relay/sink profile only after event identity, redaction, acknowledgement, and replay semantics pass their gates.
4. Observe denials, configuration failures, retries, poison rows, and uncertified outcomes in the named profile.
5. Promote only with cross-tenant, anti-enumeration, zero-downstream-call, crash/replay, redaction, and recovery evidence.

## Evidence and acceptance

The five contract shapes in this packet were accepted on 2026-10-10 on the decision recorded in `21-g0-owner-decision-record.md`, and the status ledger records the accepted scope and its limitations. The acceptance covers contract text and safety semantics; the runtime evidence each row names is still required before a runtime claim, and no runtime seam is promoted by it. Local unit tests alone do not establish hosted or HA acceptance.

Required evidence for this slice:

- Same-org agent-scoped token selecting another agent is denied before agent lookup/provider/context/tool work.
- Matching agent selection succeeds.
- Staging and production router construction rejects a missing verifier.
- Organization-scoped token behavior remains covered.
- Idempotency contract tests cover same-body replay, body mismatch, cross-tenant isolation, and uncertain completion semantics as each operation is implemented.
- Evidence tests cover redaction rejection/classified references, atomic run/outbox behavior, sink deduplication, tombstone replay fencing, and non-vacuous recovery accounting before any evidence claim is promoted.

## Consequences

- The proxy and AuthService contain deliberate defense-in-depth checks.
- Agent-scoped tokens cannot be used to select a different agent in the same organization.
- A future cross-agent delegation mechanism must be explicit rather than inferred from organization membership.
- G0's contract shapes are accepted; its runtime seams remain provisional until the evidence each ledger row names is recorded.
