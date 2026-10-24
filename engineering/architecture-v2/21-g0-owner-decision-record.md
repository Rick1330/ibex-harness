# G0 Owner Decision Record

**Status:** Accepted for contract shape only; runtime seams remain `provisional`.

**Decision date:** 2026-10-10

**Next review:** 2026-11-10, or earlier if the supported profile, authority, key set, retention policy, or evidence semantics change.

**Scope:** Principal/agent binding, policy freshness, idempotency, evidence publication, privacy controls, and the memory historical-candidate boundary.

## 1. Decision required

The owner has resolved the G0 contract decisions below. This acceptance freezes the contract shape and safety semantics only. It does not certify runtime implementation, hosted deployment, HA recovery, or any G1-G4 gate.

| Decision | Accepted decision | Required owner |
|---|---|---|
| Principal and agent binding | AuthService-issued `PrincipalContext` is the authoritative binding for every request and run. The proxy may not infer tenant or agent identity from user-controlled fields. Token-bound agent mismatch denies before lookup. | Elshaday Mengesha / Rick1330 — 2026-10-10 |
| Policy freshness | AuthService issues an immutable `PolicySnapshot` signed by the AuthService policy-signing key set. The snapshot carries authority identity, `key_id`, snapshot ID, digest, effective epoch, issued time, and expiry. Verification accepts the current key and a bounded previous key during rotation; unknown, revoked, or expired keys fail closed. | Elshaday Mengesha / Rick1330 — 2026-10-10 |
| Idempotency | The scope is `(org_id, agent_id, operation_scope, idempotency_key)` where the verified org and agent are server-derived. The durable record stores request digest, policy snapshot digest, outcome, and lifecycle state. A digest mismatch is a typed conflict, never a replay. | Elshaday Mengesha / Rick1330 — 2026-10-10 |
| Retry and uncertainty | A retry is safe only for reads, deterministic validation, and mutations whose durable claim proves the same operation has not produced an external effect. Provider calls, notifications, exports, deletes, and any external side effect require reconciliation by operation ID after an ambiguous outcome. The default response is typed `uncertified` with durable reconciliation state only for an explicitly degraded profile; otherwise fail with dependency-unavailable and never report success. | Elshaday Mengesha / Rick1330 — 2026-10-10 |
| Evidence publication | Evidence uses canonical JCS bytes, producer-specific redaction, authoritative resource identity, and a deletion/tombstone fence. Missing safety metadata is quarantined from projection. Durable-before-ack is the default. | Elshaday Mengesha / Rick1330 — 2026-10-10 |
| Privacy and deletion | Redaction class is mandatory at the producer boundary. The canonical lifecycle authority is the PostgreSQL resource-lifecycle record owned by the service responsible for the resource: proxy for request/session, memory for memory, and the future run/control-plane owner for run. The platform data layer provides the transactionally checked fence; no sink infers deletion authority. | Elshaday Mengesha / Rick1330 — 2026-10-10 |
| Memory historical mode | User retrieval remains validity-fenced. Historical conflict candidates are reachable only through the write-path adapter with explicit org and agent predicates; the general read API cannot select historical mode. | Elshaday Mengesha / Rick1330 — 2026-10-10 |
| Acting assignment | Rick1330 is the acting owner across all listed roles for this acceptance. The assignment must be replaced and re-reviewed if an individual role owner or reviewer changes. | Elshaday Mengesha / Rick1330 — 2026-10-10 |

## 2. Resolved decisions and rationale

### 2.1 Policy authority, signing identity, and key rotation

The AuthService policy-signing key set is the authority. Each snapshot names `authority`, `key_id`, and `algorithm`; the signature covers the immutable snapshot ID, digest, effective epoch, issued time, expiry, and protected scope. Key rotation publishes the new key before issuing snapshots with it, overlaps the previous key for the maximum accepted snapshot age plus clock skew, then revokes the old key. Consumers reject unknown, revoked, algorithm-mismatched, or malformed keys. The first runtime seam remains local/provisional and does not claim a deployed key service or hosted rotation evidence.

This follows the repository's existing AuthService/JWT keyset and `kid` trust pattern: verification is against an authority-owned key set, not a caller-provided key or cache. A cache may improve availability but cannot widen authority or extend expiry.

### 2.2 Maximum snapshot age by operation class

The accepted local/protected profile uses these bounds:

| Operation class | Maximum age | Stale/missing behavior |
|---|---:|---|
| Protected read or context assembly | 60 seconds | Deny or return typed verifier/policy-unavailable before downstream retrieval. |
| Mutating or externally effectful request | 30 seconds | Deny; do not invoke the provider, tool, queue mutation, or external side effect. |
| Asynchronous worker continuation | 5 minutes from the durable claim | Reconcile the operation and obtain a fresh snapshot before any new effect; never extend the original authority silently. |

Age is measured from `issued_at` using bounded clock skew of 5 seconds. Expiry is always authoritative: an expired snapshot is invalid even if its age is within the class bound. These are contract defaults for the accepted local/protected profile, not measured latency or hosted SLO claims.

### 2.3 Replay safety after worker crash

The operation state and effect class determine recovery:

| Effect class | Crash/retry rule |
|---|---|
| Read-only or deterministic validation | Safe to replay after a durable claim; same operation ID and body digest are reused. |
| PostgreSQL/outbox transaction | Safe to reconcile by operation ID; replay only if the durable record proves no commit. |
| Idempotent sink delivery | Safe to retry with `(org_id, event_id, aggregate_seq)` dedupe and the authoritative fence. |
| Provider request, notification, export, delete, or unknown external effect | Never blind-retry after an ambiguous result; reconcile by operation ID and return typed `uncertified` only where the profile permits it. |

A worker lease expiry does not prove that an external effect did not happen. The durable record remains `uncertain` until reconciliation or an explicit terminal failure is recorded.

### 2.4 Deletion-fence authority

The resource-owning service is responsible for creating and advancing the resource lifecycle record, while the PostgreSQL platform/data layer owns the transaction and exposes the authoritative org-scoped fence check. Request and session fences originate in the proxy's canonical lifecycle writes; memory fences originate in the memory service; run fences remain deferred until a run/control-plane owner and durable run contract are separately accepted. ClickHouse, Redis, OTel, caches, and event payloads are never deletion authorities. A sink must check the fence in the same transaction as projection or fail closed when it cannot.

### 2.5 Evidence retention and legal hold

The accepted baseline for evidence envelopes and operational projections is **30 days after `occurred_at`**. A legal hold, incident hold, or regulatory preservation requirement supersedes expiry and blocks deletion until explicitly released by the authorized owner. The retention clock does not authorize raw-content capture: secrets, tokens, prompts, memory bodies, embeddings, and unredacted PII remain prohibited from ordinary evidence. Sensitive approved artifacts require a separate retention class and access-controlled reference. Retention is a contract default for the local/protected profile; tenant-specific or regulatory extensions require an explicit policy and re-review.

## 3. Acceptance conditions

The following conditions are satisfied for contract-shape acceptance:

1. A named acting owner and date are present for every decision row.
2. Policy authority, key identity/rotation, freshness bounds, and stale behavior are explicit.
3. Replay-safe and reconciliation-required operation classes are explicit.
4. Producer-specific lifecycle ownership and the fail-closed fence rule are explicit.
5. Redaction, durable-before-ack, typed uncertainty, and retention/legal-hold semantics are explicit.
6. Runtime implementation, hosted/HA recovery, and production deployment remain separately evidenced gates.

**G0 accepted by Rick1330 (acting owner, all roles) on 2026-10-10, review window closed early by owner authorization.**

## 4. Non-decisions and limitations

This acceptance does not authorize runtime policy propagation, public API exposure of historical memory search, evidence relay enablement, a durable RunEnvelope, atomic budget reservation, provider expansion, MCP governance, control-plane side effects, or changes to cryptographic algorithms. The first implementation seams may be additive and are `provisional` until their required tests and evidence accumulate.

No claim is made here that the contract is hosted, HA-capable, production-supported, or G1-G4 complete. The next review is 2026-11-10, or earlier on material contract/profile change.

## 5. Evidence expected at review

- `22-evidence-production-and-verification.md`
- `contracts/jcs-canonicalization.md`
- `contracts/jcs-test-vectors.json`
- `drafts/principal_context_v0.proto`
- `contracts/g0-test-matrix.md`
- Focused unit/integration evidence in the implementation branches, with limitations recorded.
