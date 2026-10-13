# G1–G7 Contract Packet (Proposed, Round 4)

**Status:** proposed contract specifications only; no runtime wiring in this round.  
**Owner:** role owners recorded in the contract registry; individual confirmation and review dates remain governed by `21-g0-owner-decision-record.md`.  
**Source:** Round 4 research synthesis (`24-round4-architecture-research-synthesis.md`) and the owner-provided 2026-10-13 execution packet.

## Scope and compatibility

These contracts are additive `v1` proposals. They do not close GAPs, create a durable RunEnvelope, enable the ClickHouse pilot in production, implement the console, or authorize hosted/HA claims. Unknown fields and item types must be preserved where the wire protocol permits it. Rollout is expand → dual-read/write → backfill → verify → contract; rollback stops new writers and preserves replayable records.

## Required registry fields

| ID / owner | Source / version / compatibility | Scope and trust | Failure, deadline, retry | Idempotency / privacy / lifecycle | Tests and evidence |
|---|---|---|---|---|---|
| `provider-capability-manifest.v1` / Provider + Platform | LiteLLM/OpenRouter patterns; additive JSON Schema draft below | Provider/model/endpoint identity; manifest is a preflight hint, never an execution guarantee | Unknown/expired manifest yields `capability_unknown`; caller deadline and TTL bound refresh; no silent promotion of provider booleans | Key `(provider, model, endpoint, contract)`; provenance and confidence retained; no secrets or raw prompts | Three fixtures: native, adapter-needed, partial/unknown; expiry, mapping, model-vs-provider negative tests |
| `responses.v1` / Provider + Proxy | OpenAI Responses semantics; separate from Chat Completions | Ordered heterogeneous output items; unknown item types preserved | Typed parse/transport errors; absolute deadline; retry only before an acknowledged semantic event or by provider idempotency policy | `previous_response_id`, `call_id`, and server operation key are distinct; opaque reasoning is not exposed as visible chain-of-thought | Golden non-stream and SSE event vectors; multi-call tool loop; replay; unknown item |
| `memory-revision-ledger.v1` / Memory + Data | Mem0 history and LangGraph/checkpointer separation | Append-only tenant/agent-scoped long-term memory; checkpoints remain resumable workflow state, not ledger truth | CAS conflict is typed `revision_conflict`; deadline/cancel aborts append; retry reconciles by idempotency key | `(org_id, memory_id, idempotency_key)` plus expected revision; TTL is cleanup only; tombstones/retractions retained through policy horizon | Add/revise/retract/expire, duplicate, CAS, cross-tenant, checkpoint separation |
| `mcp-gateway-policy.v1` / Security + Platform | MCP auth/security patterns; deny-by-default | Audience-bound OAuth and per-tool scopes enforced at gateway; annotations advisory only | Deny on missing/stale descriptor or policy; per-tool deadline, byte/result/concurrency/rate/session budgets; mutation requires approval/step-up | No token passthrough; descriptor hash pinned to server identity/version; audit envelope retained per policy | Read-only allow/deny, mutation step-up, descriptor change, budget, management-plane isolation |
| `console-read-model.v1` / Console + API | Next.js DAL/Server Components and TanStack hydration patterns | Server-only BFF returns minimal authorized DTO plus provenance; browser cache is not authority | Distinguish observed/stale/refreshing/pending/failed/optimistic; request deadline and source timeout are bounded | Read model keyed by authorized scope and source version; no client-generated authoritative status | Unauthorized DTO, stale/fresh, optimistic rollback, correlation/provenance, cache invalidation |
| `clickhouse-sink-production.v1` / Evidence Ops + Data | ClickHouse ReplacingMergeTree and #968 pilot; follow-up only | Projection, never canonical authority; PostgreSQL ledger/fence remains authoritative | Retry transient delivery; poison permanent unsafe/fence failures; stop safely when fence unavailable | Stable `(tenant_id, source_id, event_id)`, monotonic `source_version`, deterministic insert token; tombstones retained through replay horizon | Changed block sizes, duplicate/reordered updates, delete then stale event, replica failover, shard routing, dedupe-window expiry |

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

**Explicit non-closure:** all six rows remain proposed; no runtime adapter, migration, UI, gateway, production sink, or GAP closure is included in this packet.
