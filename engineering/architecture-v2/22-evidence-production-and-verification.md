# Evidence Production and Verification Design

**Status:** Design only; runtime relay and projection remain disabled until G0 approval.

## 1. Trust boundary

Evidence is produced at the service boundary that owns the event. Producers must emit a typed, sanitized envelope; the relay must reject envelopes that cannot prove tenant scope, resource identity, redaction safety, or lifecycle authority.

```text
request/run/memory producer
        │  typed event + producer sanitizer
        ▼
canonical envelope (JCS bytes + digest)
        │  schema, scope, fence, redaction validation
        ├── invalid/quarantined store (operator review)
        └── durable relay → projection/search/index
```

## 2. Required envelope fields

| Field | Requirement | Verification |
|---|---|---|
| `event_id` | UUIDv7 or equivalent unique ID | format and uniqueness |
| `event_type` / `schema_version` | allowlisted producer contract | registry lookup |
| `org_id` | authoritative tenant binding | compare with producer context and policy snapshot |
| `resource_type` / `resource_id` | stable identity owned by the producer | producer-specific existence check |
| `producer` / `producer_version` | identifies code path and sanitizer | allowlist and deploy metadata |
| `occurred_at` | event time, not relay time | clock-skew bounds |
| `redaction_class` | mandatory; `unclassified` is non-projectable | policy matrix |
| `tombstone_fence` | authoritative resource-version/deletion fence | monotonicity and deletion check |
| `policy_snapshot_id` / `policy_digest` | decision authority at production time | freshness and digest verification |
| `payload` | producer-approved schema only | JCS canonicalization and schema validation |
| `payload_digest` | digest of canonical payload bytes | recompute and compare |

## 3. Redaction classes

- `public_metadata`: identifiers and status fields explicitly approved for broad operational views.
- `tenant_metadata`: tenant-scoped operational metadata; no secrets or raw user content.
- `sensitive_content`: content-bearing data; projection requires purpose, retention, and access policy.
- `secret`: credentials, bearer tokens, provider keys, or raw authorization material; never emitted.
- `unclassified`: quarantine-only; no relay or projection.

Sanitization is producer-specific. A relay must not infer that a payload is safe from field names or from a request ID.

## 4. Verification stages

1. **Envelope validation:** required fields, schema version, tenant scope, and event identity.
2. **Canonicalization:** serialize the payload with RFC 8785-compatible JCS rules; compute the declared digest over exact UTF-8 bytes.
3. **Authority check:** verify the policy snapshot ID, digest, authority identity, and freshness window.
4. **Lifecycle check:** verify the tombstone fence against the authoritative store. A stale event cannot resurrect a deleted resource.
5. **Redaction check:** apply producer allowlist and reject secrets, unclassified payloads, and unsupported fields.
6. **Idempotency check:** `(event_id, payload_digest)` is replay-safe; same event ID with a different digest is a conflict.
7. **Projection:** only verified events enter indexes or operator views. Quarantined events remain auditable but are not discoverable as facts.

## 5. Failure semantics

| Failure | Action | Operator signal |
|---|---|---|
| Missing/unknown schema | quarantine | `evidence_schema_rejected` |
| Digest mismatch | quarantine and raise integrity alert | `evidence_digest_mismatch` |
| Stale policy snapshot | do not project; retry only if policy allows | `evidence_policy_stale` |
| Missing redaction class | quarantine | `evidence_redaction_missing` |
| Missing or stale tombstone fence | quarantine; never infer deletion authority | `evidence_fence_missing` |
| Duplicate exact event | acknowledge as replay | `evidence_replay` |
| Same event ID/different digest | quarantine and page | `evidence_id_conflict` |

## 6. Traceability and tests

Every projected item must be joinable to `event_id`, `payload_digest`, `policy_snapshot_id`, producer version, and tombstone fence. The verification test matrix must cover positive, replay, digest-conflict, stale-policy, stale-fence, cross-tenant, secret-redaction, and canonicalization cases.

The design intentionally does not enable the existing producer rows that lack `redaction_class` and `tombstone_fence`; those rows remain outside the projection until producer-specific sanitizers and authoritative fences are approved.
