# Memory Lifecycle, Provenance, and Deletion

**Status:** `specified`; typed projection implementation is not yet certified.

## Lifecycle

```text
authenticated source → validate/scope/size → PII and safety checks
→ candidate observation → exact idempotency/hash dedup
→ near-duplicate/temporal/conflict analysis
→ active projection | quarantine/review | supersede | expire | delete
```

Every observation records tenant/resource scope, actor/source, content hash, observed/processed/valid times, source span or artifact reference, status, retention/legal hold, model/embedding/preprocessing identities, and links to duplicates, conflicts, or supersession.

Observations are append-only where retention permits; active projections are rebuildable views. Candidates and quarantine are never default-retrieved. Procedural or policy-affecting promotion requires explicit review/authority.

## Operations

Each mutation has a tenant-bound idempotency key, durable operation ID, queued/running/succeeded/failed/cancelled state, retry policy, and evidence ID. Read-after-write behavior is explicit: an acknowledged write either has a defined immediate visibility guarantee or returns operation status.

## Deletion

Deletion creates an authoritative tombstone that immediately blocks reads and cache use. An idempotent fan-out removes or redacts PostgreSQL, vectors, Redis, object artifacts, exports, analytics projections, and derived indexes according to retention and legal hold. Completion is a certificate containing per-store acknowledgements, failures, retries, and policy/hold state. Legal hold blocks physical purge but never restores retrieval eligibility.
