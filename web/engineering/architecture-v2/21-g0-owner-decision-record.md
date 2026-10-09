# G0 Owner Decision Record

**Status:** Draft for owner review — not an acceptance record

**Review window:** 2026-10-22

**Scope:** Principal/agent binding, policy freshness, idempotency, evidence publication, privacy controls, and the memory historical-candidate boundary.

## 1. Decision required

The next implementation slice must not be treated as production-accepted until the named owners confirm the decisions below. This record deliberately separates **implemented evidence** from **owner approval**.

| Decision | Recommended candidate | Required owner |
|---|---|---|
| Principal and agent binding | AuthService-issued `PrincipalContext` is the authoritative binding for every request and run; the proxy may not infer tenant or agent identity from user-controlled fields. | Auth/Proxy |
| Policy freshness | AuthService/enforcement-plane issues an immutable `PolicySnapshot` containing snapshot ID, digest, effective epoch, authority identity, and expiry. Stale or missing snapshots fail closed for protected actions. | Auth/Architecture |
| Idempotency | Key scope is `(org_id, agent_id, operation, idempotency_key)`; the durable record stores request digest, policy snapshot digest, outcome, and lifecycle state. A digest mismatch is a conflict, never a replay. | Auth/Data |
| Retry and uncertainty | A retry is permitted only while the durable record is `pending` and the operation's retry policy permits it. If the external side effect may have happened but its outcome is not certified, return profile-approved `202` with `outcome=uncertified`; never silently log-and-continue. | Architecture/Proxy |
| Evidence publication | Evidence uses canonical JCS bytes, producer-specific redaction, an authoritative resource identity, and a deletion/tombstone fence. Missing safety metadata is quarantined from projection. | Evidence/Security |
| Privacy and deletion | Redaction class is mandatory at the producer boundary. Deletion is represented by an authoritative tombstone fence and is enforced before projection, replay, export, and operator views. | Security/Privacy |
| Memory historical mode | User retrieval remains validity-fenced. Historical conflict candidates are reachable only through the write-path adapter, with explicit org and agent predicates. | Memory/Context |
| Acting assignment | Rick1330's acting assignment remains provisional until the review window closes; replacement names and expiry must be recorded if any role changes. | Architecture |

## 2. Acceptance conditions

Approval requires all of the following in the review record:

1. A named owner and reviewer for every row above.
2. An explicit freshness duration and stale-state behavior for `PolicySnapshot`.
3. An approved retry table for each operation class, including the uncertain-outcome response.
4. A producer-specific redaction schema and resource-identity source for every evidence producer.
5. Confirmation that the memory historical mode is internal-only and that direct org/agent fencing is tested.
6. A review expiry or re-review trigger; test results do not substitute for owner approval.

## 3. Non-decisions

This record does **not** authorize runtime policy propagation, public API exposure of historical memory search, evidence relay enablement, or changes to cryptographic algorithms. Those changes require a subsequent implementation record after approval.

## 4. Evidence expected at review

- `22-evidence-production-and-verification.md`
- `contracts/jcs-canonicalization.md`
- `contracts/jcs-test-vectors.json`
- `drafts/principal_context_v0.proto`
- `contracts/g0-test-matrix.md`
- Focused unit/integration evidence in the implementation branches, with limitations recorded.

## 5. Open questions to resolve

- What exact authority identity signs a `PolicySnapshot`, and which key/version is used for rotation?
- What is the maximum acceptable snapshot age per operation class?
- Which operations are safe to replay after a worker crash, and which require reconciliation?
- Which producer owns the authoritative deletion fence for request, session, memory, and run resources?
- What is the minimum evidence retention period before legal hold and deletion policy are applied?

**No row is `shipped-accepted` until these questions are answered and the owner/reviewer names are recorded.**
