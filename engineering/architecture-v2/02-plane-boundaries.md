# Plane Boundaries and Authority Matrix

**Status:** `specified` target boundary.

| Responsibility | Owner | Canonical authority | Explicit non-responsibility |
|---|---|---|---|
| Token issuance/revocation/validation | AuthService | Auth database/keyset | Provider routing or memory ranking |
| Final request authorization | Enforcement | Policy snapshot + verified principal | Model confidence or retrieval score |
| Budget reservation | Enforcement + control state | Durable reservation ledger | Local memory or Redis alone |
| Context retrieval/packing | Context plane | Authorized memory/session stores | Granting visibility |
| Provider capability | Provider plane | Immutable deployment manifest | Inferring capability from model name |
| Audit/evidence acceptance | Evidence/control | Transactional outbox and canonical event state | OTel exporter alone |
| Analytics query | Evidence projection | ClickHouse with mandatory tenant filter | Cross-tenant raw SQL |
| Large/redacted artifact | Evidence/control | Object store + metadata/tombstone | Untracked local file |
| Tool execution | Governed executor | Tool registry + policy + approval | LLM or MCP description |
| Model recommendation | Async intelligence | Versioned model artifact + evidence | Authorization, deletion, budget |
| Operator action | Management API | Policy + operation state | UI or direct database |

## Authority lattice

`verified principal → policy snapshot → capability admission → reservation → authorized context → provider/tool execution → evidence/reconciliation`.

A downstream layer cannot manufacture authority that an upstream layer did not grant. Missing, stale, ambiguous, or mismatched security state is a deny/no-route result.

## Cross-plane rules

1. Every call carries a verified `PrincipalContext` and `RunEnvelope`.
2. Every mutation has an idempotency key and durable operation ID.
3. Every external or model-produced body is data with a trust label.
4. Every projection is rebuildable or explicitly marked non-rebuildable.
5. Every fallback names whether it is security-safe, quality-degraded, or uncertified.
