# Contract Registry and Ownership

**Status:** `specified`; inventory must be completed before new boundary work. The initial G0 registry packet is proposed in ADR-0084 and tracked by issue #935; no G0 exit is claimed.

## Contract hierarchy

- **Protobuf/gRPC:** internal multi-consumer service contracts.
- **OpenAPI/REST:** external management and resource APIs under `/v1`.
- **Provider contracts:** separately versioned Chat Completions and Responses subsets plus native adapter semantics.
- **MCP schemas:** versioned tools/resources with explicit scopes and limits.
- **Events:** durable evidence and operation envelopes.
- **Database schemas:** lifecycle and authority contracts, not merely ORM models.

## Required registry fields

| Field | Required |
|---|---|
| Contract ID and owner | Yes |
| Source path and generated artifacts | Yes |
| Version and compatibility class | Yes |
| Auth/permission/resource scope | Yes |
| Status class and deployment profile | Yes |
| Error and retry behavior | Yes |
| Idempotency/deadline/cancellation | Where applicable |
| Tests and evidence link | Yes |
| Deprecation/support window | Public contracts |
|---|---|

## Proposed G0 registrations

The following registrations are the first review packet for the principal, replay, evidence, and relay foundation. They remain `proposed` until G0 owners approve the authority, compatibility, profile, and evidence fields. The entries are intentionally additive and do not authorize runtime implementation before G0 exit.

| Contract ID and owner | Source path and generated artifacts | Version / status | Scope and failure behavior | Tests and evidence |
|---|---|---|---|---|
| `principal-context.v1` — Auth/Proxy | `packages/proto/proto/ibex/auth/v1/auth.proto`; proxy/auth request context | v1 / proposed | Verified org and subject context; token-bound agent mismatch denies before lookup; missing verifier fails staging/production router construction | `agent_middleware_test.go`, `validate_agent_test.go`, `router_must_test.go`; profile evidence pending |
| `run-envelope.v1` — Architecture/Proxy | Architecture-v2 principal/run contract; additive boundary mapping pending G0 | v1 / specified, not implemented | Correlation and lineage only; resume/retry revalidates principal, policy, resource, and approval state | Cross-boundary contract matrix pending |
| `idempotency-operation.v1` — Platform/Data | Existing operation-specific idempotency stores; durable schema pending G0 | v1 / proposed | Tenant-bound key and canonical body hash; same body replays, changed body conflicts, ambiguous completion reconciles by operation ID | Operation-specific crash/replay suites pending |
| `evidence-envelope.v1` — Evidence/Platform | `packages/evidenceoutbox/store.go`; `infra/migrations/postgres/000036_evidence_plane.up.sql`; generated event artifacts pending | v1 / proposed | PostgreSQL is canonical; stable operation/event/aggregate identity, redaction classification, payload digest, tenant scope, and explicit acknowledged/uncertified behavior | `store_integration_test.go`, evidence session tests; redaction and uncertain-commit evidence pending |
| `evidence-relay-sink.v1` — Evidence/Operations | `packages/evidenceoutbox/relay.go`; selected relay entry point and sink adapter pending | v1 / proposed | At-least-once delivery with stable event+aggregate version dedupe, tenant predicates, retry/poison state, tombstone fence, and recoverable checkpoint | `relay_unit_test.go`; real sink, ack-loss, tombstone, and restore evidence pending |

## Required fields for the G0 packet

Each proposed row must be completed before acceptance with: named owner; source path and generated artifacts; version and compatibility class; authenticated scope and trust labels; deployment profile and dependencies; stable error/status mapping; deadline/cancellation and retry behavior; idempotency/body-hash and replay/conflict semantics; redaction/retention/deletion behavior; tests and evidence artifact; migration and rollback/roll-forward plan where applicable; and owner decision/review window.

### Proposed completion matrix for issue #935

The following values are the review baseline, not implementation evidence. Items marked pending require an owner decision before G0 can be accepted.

| Contract | Compatibility / scope / trust | Profile and dependencies | Errors / deadline / retry | Identity / privacy / lifecycle | Owner / evidence / review |
|---|---|---|---|---|---|
| `principal-context.v1` | Additive protobuf mapping; protected internal RPC; only AuthService-verified principal fields grant authority; caller selectors are non-authoritative | Named protected profile pending; AuthService verifier, proxy, context server; local fakes excluded from protected profile | Missing/stale/mismatched context: deny or typed 503 before downstream work; absolute deadline and cancellation propagate; auth failures are not retried | No caller overwrite; `org_id` and resource scope are explicit; no raw token/content in logs/evidence | Auth/Proxy + Context owners pending; zero-call/cross-tenant/mixed-version artifacts pending; review date pending |
| `run-envelope.v1` | Specified lineage-only contract; additive event fields; never a permission grant | No runtime profile until separately approved; depends on PrincipalContext and policy snapshot | Retry/resume/fork revalidate principal, policy epoch, resource, and approval; stale state denies; cancellation is operation-specific | Distinct run/attempt/operation IDs; durable lifecycle, approval consumption, and deletion rules deferred | Architecture/Proxy owners pending; contract matrix pending; review date pending |
| `idempotency-operation.v1` | Operation/resource scoped; tenant-bound; additive per operation; trust comes from verified org and server canonicalization | PostgreSQL authority pending operation-specific approval; Redis may cache only if non-authoritative | Typed conflict on changed body; ambiguous completion reconciles by operation ID; retry only after idempotency claim; deadline/cancellation explicit per operation | Key tuple is `(org_id, operation_scope, idempotency_key)` and body fingerprint is SHA-256 over versioned canonical UTF-8 JSON (sorted object keys, no insignificant whitespace, normalized numbers); retention/TTL pending per operation | Platform/Data owner pending; replay/conflict/crash/cross-tenant artifacts pending; review date pending |
| `evidence-envelope.v1` | Proposed event schema; tenant-filtered; redaction class and payload digest are mandatory; generated artifacts pending | PostgreSQL/outbox authority; relay and selected sink are separate dependencies; current store is only a partial substrate | Durable-before-ack or explicit durable `uncertified` outcome must be selected; retry/replay is at-least-once and deduplicated | Stable event/aggregate/operation IDs, sequence/version, schema version, redaction classification, SHA-256 digest; current `RunInput` does not yet implement all fields | Evidence/Platform owner pending; transaction/redaction/uncertain-commit artifacts pending; review date pending |
| `evidence-relay-sink.v1` | Proposed at-least-once delivery; sink contract must be versioned and tenant-filtered; relay is not authority | One named relay process, least-privilege identity, and one sink pending; Postgres outbox required | Claim/retry/poison/recover stale work; cancellation and shutdown drain pending; deliver-success/ack-loss must replay safely | Sink dedupe key is stable event ID plus aggregate version/sequence; stale/tombstoned replay is rejected; retention/restore pending | Evidence/Operations owner pending; real sink/ack-loss/tombstone/restore artifacts pending; review date pending |

The current source files cited above are evidence anchors and partial substrates, not proof that the proposed fields or behaviors are already implemented. G0 acceptance requires the named owners, selected profile, generated artifacts, concrete test/recovery bundle, limitations, and review window to be filled in.

### Authority and dependency matrix

| Authority | Canonical owner | Non-authoritative inputs | Required failure behavior | Evidence needed |
|---|---|---|---|---|
| Principal and resource ownership | AuthService/enforcement plane | Caller selectors, headers, cached projections | Deny/typed 503 before downstream work | Cross-tenant, anti-enumeration, zero-call tests |
| Policy snapshot and epoch | Named policy authority | Stale cache, model/tool descriptions, memory text | Deny/503 if missing, stale, or contradictory | Snapshot identity and stale-policy negatives |
| Evidence run/outbox lifecycle | PostgreSQL / Evidence-Platform owner pending | Redis, ClickHouse, queues, telemetry | Atomic failure or explicit uncertified outcome | Transaction, replay, redaction, RLS evidence |
| Relay delivery state | Outbox plus selected sink contract | Sink response without durable acknowledgement | Retry/poison; duplicate-safe replay | Ack-loss, stale-worker, sequence/recovery evidence |
| Deletion/tombstone fence | Lifecycle owner to be named in G0 acceptance | Replayed projection/event | Reject or skip stale/tombstoned replay | Deletion/replay-negative restore evidence |

## Compatibility rules

- Protobuf field numbers and names are never reused; removed fields are reserved.
- REST remains `/v1` until a deliberate major version; additive changes require examples and compatibility tests.
- MCP tool IDs, schemas, and result shapes are versioned and hashable.
- Provider aliases resolve to immutable deployment IDs before execution.
- Breaking changes require an ADR, migration, rollback/roll-forward plan, mixed-version tests, and docs.

CI must run Buf format/lint/generate/breaking checks, OpenAPI validation, golden error tests, MCP conformance, and generated-artifact reproducibility.
