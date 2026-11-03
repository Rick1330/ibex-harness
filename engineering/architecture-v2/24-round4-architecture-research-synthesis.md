# Round 4 Architecture Research Synthesis

**Date:** 2026-10-13  
**Scope:** Provider capabilities, OpenAI Responses contracts, typed memory lifecycle, MCP gateway security, Console data binding, and ClickHouse relay deduplication.

## Executive synthesis

Across all six topics, the verified pattern is **layered normalization rather than trusting a single convenience abstraction**:

- Provider catalogs require endpoint- and model-scoped capability data.
- OpenAI Responses requires a typed ordered-item contract distinct from Chat Completions.
- Memory requires append-oriented revisions distinct from workflow checkpoints.
- MCP security requires gateway-side enforcement beyond annotations.
- Console data is a projection with freshness and provenance, not evidence by itself.
- ClickHouse `ReplacingMergeTree` is an eventual replay layer, not an exactly-once ledger.

The resulting IBEX architecture should use four explicit planes:

1. **Contract adapters** normalize provider manifests, Responses/Chat Completions, and MCP descriptors while retaining raw discriminators and provenance.
2. **Durable evidence ledger** stores append-only, schema-versioned records with deterministic idempotency keys, actor/run/thread/checkpoint correlation, revisions, tombstones, and transactional admission.
3. **Materialized projections** serve LangGraph resumability, ClickHouse queries, Console DTOs, and retrieval, each labeled with source version, observed/as-of time, freshness, and policy status.
4. **Deny-by-default policy/audit plane** enforces authorization at the actual tool/data boundary, not from UI state or advisory metadata.

The recommendations below are derived from verified source patterns. They are **not claims that any reviewed component natively supplies the full IBEX guarantee**.

## 1. Provider capability manifests

### Findings

LiteLLM separates coarse provider endpoint metadata from model- and request-type-specific capability resolution. Its provider registry has endpoint booleans, while model metadata carries context, pricing, and flags such as function calling, reasoning, response schema, vision, and system-message support. Provider configuration classes resolve supported parameters and map them per model and request type.

OpenRouter separates aggregate model metadata from provider/deployment-specific endpoint records. Endpoint records expose provider name, provider model ID, context and token limits, pricing, supported parameters, quantization, status, latency, throughput, caching, and routing details. Routing constraints such as `require_parameters`, provider order, privacy, and fallback policy are separate from capability metadata.

### IBEX recommendation

Define `provider-capability-manifest.v1` with:

- provider, model, and endpoint identity;
- separate `chat_completions` and `responses` contracts;
- availability: `native | adapter | unsupported | unknown`;
- parameter states and explicit mappings;
- request/input/output passthrough maps;
- modality, context, token, pricing, and routing limits;
- privacy and eligibility requirements;
- provenance: `observed_at`, TTL, source, and confidence.

Treat manifests as preflight hints, not guarantees. Keep native, adapted, unsupported, and unknown capabilities distinct. Do not promote provider-level booleans to model guarantees.

## 2. OpenAI Responses contract

### Findings

Responses is not Chat Completions with renamed fields. Responses uses `input`/`instructions` and an ordered heterogeneous `output[]` containing typed items such as message, reasoning, and function calls. Chat Completions uses `messages[]`, `choices[]`, nested tool calls, and a different streaming shape.

A Responses consumer must:

- dispatch on item type rather than assuming the first output item is text;
- preserve unknown item types for forward compatibility;
- support multiple function calls keyed by `call_id`;
- replay relevant completed reasoning/tool items when continuing a tool loop;
- distinguish `output_item.added` from authoritative `output_item.done`;
- aggregate semantic SSE events rather than Chat Completions delta chunks;
- preserve opaque reasoning/encrypted content without interpreting it as visible chain-of-thought.

### IBEX recommendation

Implement a narrow `responses.v1` adapter with:

- non-stream creation and `previous_response_id` support;
- normalized ordered items for message, reasoning metadata/opaque content, function call, and function output;
- a multi-call tool loop keyed by `call_id`;
- semantic streaming handlers for creation, item add/done, text delta, function-argument delta/done, completion, and error;
- raw item/event discriminators retained for forward compatibility.

Keep a separate Chat Completions adapter. Do not collapse the two wire contracts into one lossy shape.

## 3. Typed memory lifecycle and provenance

### Findings

Mem0 provides scoped extraction, retrieval, explicit update/delete operations, and useful history records containing memory ID, previous/current state, event type, timestamps, actor/run identifiers, and metadata. Its newer extraction flow is ADD-oriented; this does not itself define a safe domain conflict protocol.

LangGraph separates thread-scoped checkpoints from long-term Store values. Checkpoints support resumability, time travel, pending writes, and version tracking. Store values are JSON dictionaries under namespace/key and are backend-dependent for search, TTL, ordering, and overwrite semantics. Store overwrite behavior is not an intrinsic multi-writer conflict protocol.

### IBEX recommendation

Use LangGraph checkpointers for resumable workflow state and a separate durable typed memory ledger for long-term memory. Model memory changes as immutable, schema-versioned revisions with:

- `memory_id`, kind/type, and schema version;
- status: active, superseded, retracted, expired;
- value and source references;
- observed/recorded/valid timestamps;
- tenant, subject, agent, run, thread, and checkpoint provenance;
- confidence, content hash, retention metadata;
- `revision`, `supersedes`, `retracts`, and tombstone links.

Require idempotency keys plus expected-revision/CAS or transactional append. Use TTL only for operational cleanup, never as the semantic meaning that a fact is false. If Mem0 is used, treat it as extraction/retrieval and map every ADD/UPDATE/DELETE into the IBEX envelope.

## 4. MCP gateway security

### Findings

The reviewed gateway patterns protect management endpoints more clearly than individual proxy tools. MCP ToolAnnotations such as read-only or destructive hints are advisory and do not define a universal authorization vocabulary. Gateway authentication must not be assumed to protect upstream proxy routes or internal management handlers.

The MCP authorization model emphasizes resource/audience-bound tokens, least-privilege scopes, HTTPS, and no token passthrough for another resource. Tool servers and gateways should validate inputs, rate-limit calls, and enforce bounded execution.

### IBEX recommendation

Use a deny-by-default gateway policy with:

- audience-bound OAuth and per-tool/capability scopes;
- separate read-only and mutating roles/endpoints;
- explicit approval or step-up for mutation;
- gateway-side enforcement independent of ToolAnnotations;
- per-tool deadlines, byte/result/concurrency/rate limits, and session budgets;
- canonical descriptor hashes pinned to trusted server/version identity;
- descriptor change review and revalidation on every call;
- strict downstream credential exchange with no token passthrough;
- management-plane isolation and complete audit records.

Audit fields should include principal, server, tool, descriptor hash, policy decision, latency, bounded result metadata, and correlation ID.

## 5. Console real-data binding

### Findings

Next.js Server Components or a server-only Data Access Layer can return authorized minimal DTOs. TanStack Query can hydrate and revalidate those DTOs, but cache state, hydration, rendering, or `staleTime` cannot prove source currency, completeness, authorization correctness, or durable commit.

Optimistic updates are especially important: a query-cache value is only the browser's current state until a validated server mutation result and read-model revalidation establish a stronger status.

### IBEX recommendation

Implement a server-only BFF/DAL returning versioned minimal read models plus a provenance envelope:

- `contract_version`;
- request/correlation ID;
- source system;
- `observed_at`/`as_of`;
- freshness/age;
- authorization scope;
- server-generated result status.

Render the first view from a Server Component; use TanStack Query for interactive cache, polling, and revalidation. Use per-request server QueryClients and one browser QueryClient. Display observed, stale, refreshing, pending, failed, and optimistic states distinctly. Reserve labels such as authoritative, complete, policy-compliant, and committed for server-side authorization or durable evidence.

## 6. ClickHouse relay deduplication

### Findings

`ReplacingMergeTree` collapses rows sharing an `ORDER BY` key during eventual merges. It is not an insert-time uniqueness constraint. Correctness-sensitive reads require `FINAL`, `argMax`, or an equivalent tested materialized serving projection.

Replicated insert deduplication protects matching retry blocks or tokens only within a finite deduplication window. It does not replace a durable per-event ledger and does not solve duplicates arriving as different blocks, from different shards, or after the window expires.

Tombstone rows must remain through the proven late-data and replay horizon. Physical cleanup can allow stale events to resurrect data if performed too early.

### IBEX recommendation

Use a hybrid model:

- application ledger as the exactly-once admission boundary;
- stable `(tenant_id, source_id, event_id)` identity;
- monotonic `source_version` rather than wall-clock ordering;
- `ReplicatedReplacingMergeTree(source_version, is_deleted)` as the append/replay projection;
- deterministic insert deduplication tokens for network retries;
- stable shard routing for all versions of a key;
- current-state reads through tested `FINAL` or an equivalent `argMax`/materialized projection;
- tombstone retention through the maximum replay/late-data horizon.

Gate production on tests for changed block sizes, duplicate/reordered updates, delete followed by stale events, replica failover, shard routing, and retry deduplication-window expiry.

## Cross-topic rollout gates

Before promoting these patterns into protected or production profiles, require:

- replay, reordering, failover, and crash-window tests;
- multi-call and unknown-event tests for provider adapters;
- stale-cache and unauthorized-access tests for Console flows;
- MCP descriptor-change and per-tool authorization tests;
- cross-tenant and cross-agent negative tests for memory and evidence;
- explicit provenance, retention, legal-hold, and deletion reviews;
- source-version, observed/as-of, freshness, and policy fields on normalized records;
- durable ledger evidence before claiming exactly-once or committed outcomes.

## Source families reviewed

- LiteLLM provider endpoint/model metadata and parameter mapping documentation.
- OpenRouter model, endpoint, routing, and provider documentation.
- OpenAI Responses, function calling, reasoning, conversation-state, streaming, Python SDK, and Node SDK documentation.
- Mem0 memory operations, history, extraction, and migration documentation.
- LangGraph Store, TTL, persistence, memory, and checkpoint documentation.
- MCP authorization, security best practices, tool annotations, filesystem server, and gateway implementation references.
- Next.js data security, Server Components, Server Actions, DAL, and TanStack Query SSR/hydration/invalidation documentation.
- ClickHouse `ReplacingMergeTree`, replication, retry deduplication, and Altinity RMT/tombstone guidance.

## Relationship to the G0/GAP audit

These findings reinforce the earlier audit conclusion: catalogs, caches, SDK helpers, memory services, MCP annotations, and merge engines should remain **bounded adapters or projections**, never the canonical evidence, policy, or consistency boundary.
