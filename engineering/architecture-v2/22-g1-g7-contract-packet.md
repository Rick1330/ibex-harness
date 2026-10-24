# G1–G7 Contract Packet (Proposed, Round 4)

**Status:** proposed contract specifications only; no runtime wiring in this round.  
**Owner:** role owners recorded in the contract registry; individual confirmation and review dates remain governed by `21-g0-owner-decision-record.md`.  
**Source:** Round 4 research synthesis (`24-round4-architecture-research-synthesis.md`) and the owner-provided 2026-10-13 execution packet.

## Scope and compatibility

These contracts are additive `v1` proposals. They do not close GAPs, create a durable RunEnvelope, enable the ClickHouse pilot in production, implement the console, or authorize hosted/HA claims. Unknown fields and item types must be preserved where the wire protocol permits it. Rollout is expand → dual-read/write → backfill → verify → contract; rollback stops new writers and preserves replayable records.

## Required registry fields

The six proposed registrations below use the field set required by `03-contract-registry.md`. “Not implemented” and “not selected” are explicit status values, not implied defaults: this packet does not claim runtime wiring, generated artifacts, or a production deployment profile.

| Contract ID and owner | Source path and generated artifacts | Version / compatibility / status | Authenticated scope and trust | Deployment profile and dependencies | Failure / deadline / retry | Idempotency / privacy / lifecycle | Tests and evidence |
|---|---|---|---|---|---|---|---|
| `provider-capability-manifest.v1` — Provider + Platform | `engineering/architecture-v2/22-g1-g7-contract-packet.md:24-42`; generated artifact: **not implemented** | v1 / additive; specified, runtime **not implemented** | Provider/model/endpoint identity; manifest is an untrusted preflight hint and never an execution guarantee | Deployment profile: **not selected**; depends on provider adapters and provenance storage | Unknown/expired manifests yield `capability_unknown`; caller deadline and TTL bound refresh; no silent capability promotion; retry only through bounded refresh policy | Key `(provider, model, endpoint, contract)`; provenance/confidence retained; no secrets or raw prompts; retention/deletion policy **not implemented** | Native, adapter-needed, partial/unknown fixtures; expiry, mapping, and model-vs-provider negative tests are **required, not implemented**; research basis: `24-round4-architecture-research-synthesis.md:21-42` |
| `responses.v1` — Provider + Proxy | `engineering/architecture-v2/22-g1-g7-contract-packet.md:44-46`; generated artifact: **not implemented** | v1 / additive; specified, adapter **not implemented** | Authenticated proxy/provider operation scope; ordered output items and opaque reasoning remain data, not authority | Deployment profile: **not selected**; depends on a separate Responses adapter, provider credentials, and existing Chat Completions boundary | Typed parse/transport errors; absolute deadline; retry only before acknowledged semantic events or under provider idempotency policy | `previous_response_id`, `call_id`, and server operation key remain distinct; opaque reasoning is not exposed; retention/deletion semantics **not implemented** | Golden non-stream/SSE vectors, multi-call tool loop, replay, and unknown-item tests are **required, not implemented**; research basis: `24-round4-architecture-research-synthesis.md:44-63` |
| `memory-revision-ledger.v1` — Memory + Data | `engineering/architecture-v2/22-g1-g7-contract-packet.md:48-62`; generated artifact: **not implemented** | v1 / additive; specified, durable ledger **not implemented** | `(org_id, subject_id, agent_id)` scope from verified server context; checkpoints are workflow state, not ledger authority | Deployment profile: **not selected**; depends on PostgreSQL ledger migration and memory service integration | CAS conflict is typed `revision_conflict`; deadline/cancel aborts append; retry reconciles by idempotency key; missing authority fails closed | `(org_id, memory_id, idempotency_key)` plus expected revision; tombstones/retractions retained through policy horizon; TTL is cleanup only | Add/revise/retract/expire, duplicate, CAS, cross-tenant, and checkpoint-separation tests are **required, not implemented**; research basis: `24-round4-architecture-research-synthesis.md:65-88` |
| `mcp-gateway-policy.v1` — Security + Platform | `engineering/architecture-v2/22-g1-g7-contract-packet.md:64-66`; read-only subset: `packages/mcp_gateway/` + `services/mcp-operator/` (ADR-0086); policy store/credential exchange **not implemented** | v1 / additive; specified; read-only subset **implemented-local**, contract **not accepted** | Audience-bound OAuth and per-tool scopes at the gateway; annotations are advisory; deny by default | Deployment profile: **not selected**; depends on gateway policy store, descriptor registry, and downstream credential exchange | Deny on missing/stale descriptor or policy; bounded per-tool deadline/bytes/results/concurrency/rate/session budgets; mutation requires approval/step-up; no permissive retry | No token passthrough; descriptor hash pinned to server identity/version; audit retained per policy; secret and result-content retention **not implemented** | Read-only allow/deny, scope/bitmap, redaction, timeout, rate-limit, audit, and cross-tenant `not_found` tests **implemented locally**; mutation step-up, descriptor revalidation, budget, and management-plane isolation tests **required, not implemented**; research basis: `24-round4-architecture-research-synthesis.md:90-111` |
| `console-read-model.v1` — Console + API | `engineering/architecture-v2/22-g1-g7-contract-packet.md:68-70`; generated artifact: **not implemented** | v1 / additive; specified, BFF/read model **not implemented** | Server-only authorized DTO under the caller’s org/resource scope; browser cache is never authority | Deployment profile: **not selected**; depends on Console server components, API BFF/DAL, and source read models | Distinguish observed/stale/refreshing/pending/failed/optimistic; bounded request/source deadlines; retry only through source policy | Read model keyed by authorized scope and source version; no client-generated authoritative status; cache TTL/invalidation policy **not implemented** | Unauthorized DTO, stale/fresh, optimistic rollback, provenance, and cache invalidation tests are **required, not implemented**; research basis: `24-round4-architecture-research-synthesis.md:113-135` |
| `clickhouse-sink-production.v1` — Evidence Ops + Data | `engineering/architecture-v2/22-g1-g7-contract-packet.md:72-74`; existing pilot substrate `packages/evidenceoutbox/clickhousesink/`, migration `infra/migrations/clickhouse/000006_evidence_events.up.sql`; generated artifact: **not implemented** | v1 / additive; production sink **not selected**, pilot remains provisional/G4-gated | Projection only; PostgreSQL ledger and authoritative lifecycle fence remain canonical; tenant identity is mandatory | Deployment profile: **not selected**; depends on PostgreSQL outbox, authoritative fence checker, ClickHouse cluster, and relay role | Retry transient delivery; poison permanent unsafe/fence failures; stop safely when fence unavailable; no exactly-once claim | Stable `(tenant_id, source_id, event_id)`, monotonic `source_version`, deterministic insert token; tombstones retained through replay horizon; production retention **not implemented** | Block-size, duplicate/reorder, delete-then-stale, failover, shard-routing, and dedupe-window tests are **required, not implemented**; current pilot evidence: `packages/evidenceoutbox/clickhousesink/*_test.go` |

## Draft contract shapes

### `provider-capability-manifest.v1`

```json
{
  "contract_version": "provider-capability-manifest.v1",
  "provider": "string",
  "model": "string",
  "endpoint": "string",
  "contracts": {
    "chat_completions": {"availability": "native|adapter|unsupported|unknown", "parameters": {}, "passthrough": {}},
    "responses": {"availability": "native|adapter|unsupported|unknown", "parameters": {}, "passthrough": {}}
  },
  "limits": {"modalities": [], "context_tokens": null, "max_output_tokens": null, "pricing": {}, "routing": {}},
  "privacy": {"eligible": false, "requirements": []},
  "provenance": {"observed_at": "RFC3339", "ttl_seconds": 0, "source": "string", "confidence": "high|medium|low|unknown"}
}
```

Parameters must carry explicit states (`supported`, `unsupported`, `mapped`, `unknown`) and mappings; provider-level flags never become model-level guarantees without model/endpoint evidence.

### `responses.v1`

The normalized adapter preserves ordered `output[]` items with discriminators `message`, `reasoning`, `function_call`, `function_call_output`, and `unknown`. Each tool call is keyed by `call_id`; continuation may carry `previous_response_id`. Semantic SSE events are `created`, `output_item.added`, `output_item.done`, text delta, function-argument delta/done, `completed`, and `failed`. Raw event/item fields are retained for forward compatibility. This is not a Chat Completions delta adapter.

### `memory-revision-ledger.v1`

```json
{
  "contract_version": "memory-revision-ledger.v1",
  "memory_id": "uuid", "revision": 1, "kind": "string", "schema_version": "string",
  "status": "active|superseded|retracted|expired", "value": {}, "source_refs": [],
  "observed_at": "RFC3339", "recorded_at": "RFC3339", "valid_from": "RFC3339", "valid_until": null,
  "org_id": "uuid", "subject_id": "uuid", "agent_id": "uuid", "run_id": "string", "thread_id": "string", "checkpoint_id": "string",
  "confidence": 0.0, "content_hash": "string", "retention": {}, "supersedes": null, "retracts": null, "tombstone": null,
  "idempotency_key": "string", "expected_revision": 0
}
```

Append is accepted only when the idempotency key is new and `expected_revision` matches. LangGraph-style checkpoints remain a separate resumability mechanism.

### `mcp-gateway-policy.v1`

A policy decision binds `principal`, `audience`, `server`, `tool`, descriptor hash, scopes, role (`read_only|mutating`), approval state, deadlines, and budgets. The gateway rejects by default, revalidates descriptor hashes on change, exchanges credentials for the downstream audience, and never forwards the caller token. Audit includes principal, server, tool, descriptor hash, decision, latency, bounded result metadata, and correlation ID.

### `console-read-model.v1`

Every response is a minimal server-authorized DTO wrapped in `contract_version`, request/correlation ID, source system, `observed_at`, `as_of`, freshness/age, authorization scope, and a server-generated status: `observed`, `stale`, `refreshing`, `pending`, `failed`, or `optimistic`. `authoritative`, `committed`, and `policy-compliant` are reserved for server evidence, never browser cache labels.

### `clickhouse-sink-production.v1`

The application ledger is the exactly-once admission boundary. The projection uses stable tenant/source/event identity, monotonic `source_version`, `ReplicatedReplacingMergeTree(source_version, is_deleted)`, deterministic retry tokens, and stable shard routing. Current-state reads require tested `FINAL`, `argMax`, or an equivalent materialized projection. Tombstones remain through the maximum proven replay/late-data horizon. The merged #968 sink is a non-production pilot and does not prove the production gate.

## Evidence links and review gates

- G0 acceptance scope: `21-g0-owner-decision-record.md`.
- Open conditions: `18-gap-register.md` and `23-g0-gap-audit-report.md`.
- Research basis: `24-round4-architecture-research-synthesis.md`.
- Existing evidence relay substrate: `packages/evidenceoutbox/` and `infra/migrations/postgres/000036_evidence_plane.up.sql`.
- Required future evidence: conformance vectors, cross-tenant negatives, replay/reorder/failover tests, descriptor-change tests, freshness/authorization tests, and durable ledger proof before any exactly-once or committed claim.

**Explicit non-closure:** all six rows remain proposed and unaccepted; no runtime adapter, migration, UI, enforcement policy store, production sink, or GAP closure is included in this packet. The default-off read-only operator subset from ADR-0086/issue #1013 does not accept `mcp-gateway-policy.v1`, does not implement credential exchange or descriptor revalidation, and does not close GAP-009.
