# Engineering Audit: Trace Inspector Data-Contract Gaps

**Repository:** `Rick1330/ibex-harness`  
**Audited revision:** `5d7e0f21af402b551351e6272da7f5464e106d1b`  
**Scope:** Track D trace inspector (`4.D.2`), adjacent memory/directive/session links, request correlation, and related Track D analytics/drift contracts.  
**Method:** Repository source, proto definitions, applied migrations, engineering schema documentation, roadmap milestones, and proxy/service implementations were compared. This audit treats an item as available only when it exists at the layer the dashboard is documented to query, not merely when an internal implementation computes it.

## Executive conclusion

The six-section trace inspector cannot currently render a complete real-data view end to end. The most severe blockers are the absence of a durable, shared trace identifier on the context-assembly RPC; the lack of context-assembly stage metrics and payloads in the canonical `ibex.llm_traces` row; the lack of prompt, completion, tool arguments, and idempotency data in the persisted read models; and the fact that the applied session migration stores only message/completion hashes rather than reconstructible conversation content. The UX and milestone documents describe richer contracts than the currently queryable schemas provide.

Several values are already computed internally and can be exported additively. The context service calculates all `AssemblyMetrics` stages and internal scoring inputs, and the proxy already has request IDs, OTEL trace IDs, session IDs, and assembly timing in process. Other requirements need a migration or a new durable payload/event store, especially raw JSON, transcript reconstruction, tool arguments, and a reliable join between context assembly and the canonical trace row. The existing documentation also contains an important ambiguity: the planning schema describes `session_events` and archive pointers, but the applied Phase-2 migration creates only `sessions` and `checkpoints`.

## Contract status summary

| Inspector section or adjacent surface | Documented source | Current queryable contract | Status | Severity |
|---|---|---|---|---|
| Summary header | ClickHouse trace plus `AssemblyMetrics` | `ibex.llm_traces` has identity, model/provider, token totals, and four latency fields; no assembly stage fields | Partial | Blocks the promised latency breakdown; basic header can degrade |
| Context assembly | `ibex.context.v1` trace payload | gRPC response has budget totals, included memories, and `AssemblyMetrics`; no trace ID, directive hash, confidence, frequency, similarity, per-memory tokens, or exclusions | Partial / unjoinable historically | Blocks a trustworthy panel |
| Conversation | Session archive (MinIO) or ClickHouse | Applied checkpoints store hashes and metadata, not messages or response content; ClickHouse explicitly stores no prompt/completion | Unavailable from current canonical stores | Blocks full transcript |
| Tool calls | ATP/tool-call tracking | `mcp_tool_calls` stores name and outcome metadata only | Partial | Degrades one panel; arguments and idempotency are unavailable |
| Raw JSON | Full permission-gated trace payload | No full trace payload is persisted in the canonical trace table; prompt/completion are intentionally omitted | Unavailable | Blocks the panel except for a newly designed payload store |
| Cross-links | Memory detail, directive diff, session replay | Memory/directive IDs exist in some stores; trace-to-context and trace-to-session joins are inconsistent; replay content is not durably present in applied tables | Partial | Breaks or weakens links depending on target |
| Drift alerts | Track D `4.D.4` backing behavioral-fingerprint data | Milestone is planned and depends on a Phase 4.5 schema/API not shown as a dashboard-ready read contract | Not dashboard-ready | Blocks reliable alert detail |
| Cost/usage analytics | Track D `4.D.5` usage/billing schema | Planning text says backing schema exists, but no complete dashboard read contract is specified in the milestone | Partial / underspecified | Risks implementation against unverified fields |

## Gap 1 — Summary header cannot provide the promised context-time and full latency breakdown

**Evidence.** The UX specification promises agent, session, model, provider, total latency, proxy overhead, context time, and prompt/completion tokens (`web/engineering/UI_UX_GUIDELINES.md:202-207`). The milestone maps the summary header to “ClickHouse trace + AssemblyMetrics” (`web/content/roadmap/phase-4-multi-provider/milestones/4.d.2-trace-inspector.mdx:39-48`). The canonical `ibex.llm_traces` table contains `request_id`, `org_id`, `agent_id`, nullable `session_id`, model/provider, input/output/total tokens, `auth_latency_ms`, `directive_latency_ms`, `provider_ttfb_ms`, and `total_latency_ms`, but no `context_assembly_ms` or assembly stage columns (`web/engineering/DATABASE_SCHEMA.md:1786-1819`). The proxy’s persisted `TraceRecord` has the same limitation (`services/proxy/internal/http/trace/assemble.go:24-45`; `packages/clickhouse/record.go:10-34`).

**Mismatch.** `context_assembly_ms` is measured around the RPC in the proxy and is available in the response metadata path (`services/proxy/internal/http/chat_context_assemble.go:63-71`, `166-181`), but it is not written to `ibex.llm_traces`. The richer `AssemblyMetrics` fields—budget calculation, directive load, hot/cold retrieval, ranking, packing, formatting, total, and candidates evaluated—exist in the context proto (`packages/proto/proto/ibex/context/v1/context.proto:54-64`) and are computed by the context service (`services/context/app/assemble.py:243-259`), but the proxy trace row does not carry them.

**Severity.** **High.** A basic header can show identity, token totals, provider TTFB, directive latency, and total latency. The promised historical context-time and per-stage explanation is unavailable, so the core debugging value is materially degraded.

**Change risk and cost.** Adding nullable/defaulted columns to ClickHouse and extending the trace record is additive-safe, but historical rows cannot be backfilled accurately. Exporting the already-computed assembly metrics is cheap at write time. A new correlation key is required before these fields can be reliably joined from a separate assembly store.

**Existing/deferred status.** This is one of the five known gaps in the request. The richer metrics are explicitly a prerequisite for `4.D.2` (`4.d.2-trace-inspector.mdx:83-89`), but no applied trace-storage migration persists them.

## Gap 2 — Context assembly has no durable correlation key to the canonical trace row

**Evidence.** `AssembleContextRequest` contains agent, organization, session, query, model, directive version, token budget, recent messages, and options, but no `request_id`, `trace_id`, or `span_id` (`packages/proto/proto/ibex/context/v1/context.proto:21-31`). `AssembleContextResponse` likewise has no identifier (`:43-52`). The proxy builds context parameters from tenant IDs, model, query, and messages only (`services/proxy/internal/http/chat_context_assemble.go:119-130`). In contrast, `ibex.llm_traces` is keyed operationally by `request_id` and may include `session_id` (`web/engineering/DATABASE_SCHEMA.md:1791-1798`).

**Mismatch.** The proxy can expose an OTEL `trace_id` in the non-streaming response metadata (`web/engineering/API_DOCUMENTATION.md:2456-2465`), and request IDs are propagated elsewhere, but the context RPC contract does not receive either value. A dashboard cannot prove that an `ibex.context.v1` payload belongs to a particular `ibex.llm_traces` row by joining the documented fields. `session_id` is not sufficient because multiple turns share a session.

**Severity.** **Critical.** This blocks a trustworthy context-assembly panel and prevents joining stage metrics, selected memories, exclusions, and directive data to one user-facing inference.

**Change risk and cost.** Adding `request_id` and/or `trace_id` to the request and echoing it in the response is additive-safe in proto3. Propagating the value through the context client, context service logs/events, and ClickHouse writer is cheap relative to a new computation. Existing historical assembly records cannot be relinked without a separate heuristic and should not be guessed.

**Existing/deferred status.** This is a known gap in the request. The API already exposes a trace ID only in the proxy response metadata (`API_DOCUMENTATION.md:2456-2497`); it does not establish the context-RPC-to-ClickHouse join.

## Gap 3 — Per-memory score contract does not match the UX or the scoring implementation

**Evidence.** The UX requires rank, composite score plus components, category, confidence, and usefulness (`web/engineering/UI_UX_GUIDELINES.md:208-214`). The proto `MemoryUsed` exports only memory ID, composite score, relevance, recency, usefulness, rank, and category (`packages/proto/proto/ibex/context/v1/context.proto:66-74`). It omits confidence, access frequency, raw similarity, per-memory token count, and any inclusion/exclusion reason. The context implementation’s `MemoryUsedRecord` mirrors this incomplete shape (`services/context/app/assemble.py:55-66`, `178-188`).

**Mismatch.** More importantly, the context service currently labels its local value as an interim score: `0.85 * similarity + 0.15 * confidence`, explicitly distinct from the memory service’s five-factor composite score (`services/context/app/scoring.py:1-14`, `28-45`). The packer repeats that distinction and says the real memory-service composite is unavailable until it is exposed on the wire (`services/context/app/packer.py:35-43`). Therefore, a dashboard field called “composite score” would be misleading if it is populated from the context-local interim score.

**Severity.** **High.** The panel can show a ranked included-memory list, but cannot satisfy the promised auditable weighted score breakdown or explain rank-versus-similarity divergence. The lack of excluded candidates prevents explaining why plausible memories were not selected.

**Change risk and cost.** Adding fields to `MemoryUsed` is additive-safe. Exporting confidence and the real composite is cheap if the memory service already computes them, but access frequency, raw similarity, token count, candidate disposition, and exclusion reason must be carried through retrieval, scoring, packing, and response construction. An excluded-candidate repeated message is also additive-safe but may increase payload size. No historical backfill can reconstruct per-request candidate decisions from current persisted rows.

**Existing/deferred status.** The missing fields and interim-score distinction are the known memory-assembly gap. The implementation itself marks real composite export as a follow-up (`services/context/app/scoring.py:3-8`).

## Gap 4 — Directive identity is only partially available for the context panel and directive diff link

**Evidence.** The UX requires directive version ID and hash (`UI_UX_GUIDELINES.md:208-210`). The context request has `directive_version_id` (`context.proto:21-30`), and the sessions table has `directive_version_id` in both the documented model and applied migration (`DATABASE_SCHEMA.md:804-807`; `infra/migrations/postgres/000010_create_sessions.up.sql:4-16`). The 4.D.2 source table, however, says the context panel reads an `ibex.context.v1` trace payload (`4.d.2-trace-inspector.mdx:41-48`), while the response has no directive version field or hash (`context.proto:43-52`).

**Mismatch.** The request schema supports a directive ID in principle, but the proxy’s `assembleParamsFromRequest` does not populate `session_id` or `directive_version_id` (`chat_context_assemble.go:119-130`). The dashboard therefore cannot reliably obtain the exact directive identity from the assembly response or from the canonical trace row. A directive ID may be found through the session record, but that does not establish which directive was actually used on a specific turn, especially when overrides or fallback paths exist. The UX promises a hash, but no cited context or trace contract exports one.

**Severity.** **High for the cross-link and auditability; medium for the header/panel.** A link may be constructed from session metadata in simple cases, but exact per-request provenance is not guaranteed.

**Change risk and cost.** Additive proto and trace fields are safe. Populating the request from the resolved directive/session context is cheap. Persisting a hash requires a deterministic version-content hash at directive resolution time; this is a small new computation. Historical rows cannot be made exact without stored per-request directive identity.

**Existing/deferred status.** This is a new finding adjacent to the known correlation gap. Track D `4.D.4` promises a directive timeline and diff viewer, but its milestone only states that a directive versioning API is a prerequisite (`4.d.4-drift-alerts-directive-management.mdx:46-52`, `87-92`); it does not define the trace-to-version read contract.

## Gap 5 — Conversation view cannot reconstruct a full transcript from the applied session schema

**Evidence.** The 4.D.2 milestone explicitly permits “Session archive (MinIO) or ClickHouse” as the conversation source (`4.d.2-trace-inspector.mdx:41-48`). The canonical ClickHouse table explicitly stores no prompt/completion content (`DATABASE_SCHEMA.md:1786-1789`). The applied `000010` session migration stores checkpoints with `messages_hash`, token counts, model/provider, `completion_hash`, latency, provider request ID, stream/completion flags, and timestamps, but no messages or response body (`infra/migrations/postgres/000010_create_sessions.up.sql:45-80`). The proxy writes exactly a message hash and completion hash into each checkpoint (`services/proxy/internal/http/session/checkpoint.go:29-42`, `52-58`).

**Mismatch.** The engineering schema documentation describes a richer future/current-looking `checkpoints.state JSONB` containing `conversation`, completed tools, and context snapshot, and a `session_events` table whose event data can contain messages and tool arguments (`web/engineering/DATABASE_SCHEMA.md:892-979`). It simultaneously states that the Phase-2 applied subset is only hashes/metadata and that fuller columns are not yet migrated (`:780-783`). The live migration confirms that `state` and `session_events` are absent from `000010`. There is no repository evidence in the audited paths of an operational MinIO archive writer or a durable conversation payload read API.

**Severity.** **Critical.** The conversation section cannot show request messages or response content from the current canonical stores. A hash is useful for integrity/deduplication but cannot reconstruct content or ordering beyond turn metadata.

**Change risk and cost.** This requires a migration or a new archive/event store, not a pure additive dashboard change. Adding JSONB state or append-only session events is schema-additive but requires payload capture, retention, tenant authorization, and likely backfill impossibility. A MinIO archive path would require a new writer/read contract and a shared key tied to request/checkpoint IDs. Full raw content also raises the UX’s required permission gate and sensitive-data audit requirements (`UI_UX_GUIDELINES.md:229-232`).

**Existing/deferred status.** The session migration explicitly defers the fuller model (`000010_create_sessions.up.sql:1-2`; `DATABASE_SCHEMA.md:780-783`). This is a new trace-inspector blocker derived from that documented deferral.

## Gap 6 — Tool-call timeline is metadata-only and does not meet the UX fields

**Evidence.** The UX requires tool name plus arguments, idempotency key, and status/outcome (`UI_UX_GUIDELINES.md:218-221`). The applied ClickHouse table has `request_id`, organization/agent, tool name, latency, success, error code, and timestamp only (`DATABASE_SCHEMA.md:1822-1843`). The MCP audit emitter inserts exactly those columns and documents itself as metadata-only (`services/mcp-memory/app/audit.py:33-37`, `40-80`). The idempotency key is used in outbound memory client headers but is not emitted in the audit event (`services/mcp-memory/app/clients/memory.py:195-203`; `audit.py:40-49`).

**Mismatch.** Tool name, latency, success, and error code exist. Tool arguments and idempotency key do not exist in the dashboard’s documented source. A tool call can be correlated to `request_id` only when the originating request ID is the same and the event is emitted on that path; the auth-rejection path creates a fresh random request ID (`services/mcp-memory/app/middleware.py:151-165`). The current table also does not contain a session ID, trace ID, call sequence, start/end pair, or a durable result/outcome payload beyond a boolean and error code.

**Severity.** **High for a useful debugging timeline; medium if the panel is intentionally reduced to metadata.** The panel can list tool names and outcomes but cannot explain what arguments caused behavior or guarantee chronological ordering among calls sharing a timestamp.

**Change risk and cost.** Adding nullable `args_json`/sanitized arguments, `idempotency_key`, sequence or start time, session ID, and trace ID is additive-safe at the schema level. Argument capture requires explicit sanitization/redaction and retention policy; outcome payload capture may require new computation and security review. Existing rows cannot be backfilled.

**Existing/deferred status.** This is a known gap. The schema states that Phase 3.5.E.4 must expand the table rather than recreate it (`DATABASE_SCHEMA.md:1822-1825`), so the required migration is already named as a deferred follow-up.

## Gap 7 — Raw JSON panel has no full trace payload to read

**Evidence.** The UX requires a sanitized payload and a permission gate (`UI_UX_GUIDELINES.md:222-232`). The 4.D.2 milestone calls its source the “Full trace payload” (`4.d.2-trace-inspector.mdx:41-48`) and requires `trace:read_raw` gating (`:71-79`). The canonical ClickHouse trace table explicitly omits prompt/completion content (`DATABASE_SCHEMA.md:1786-1789`), and the trace record comments say content is intentionally omitted (`packages/clickhouse/record.go:10-13`). The applied checkpoints store only hashes, not payloads (`000010_create_sessions.up.sql:45-67`).

**Mismatch.** No audited durable store contains a full, sanitized, per-request trace envelope combining request metadata, context assembly, messages, tool events, and response. The proxy response can embed only a small `ibex` metadata object when configured, and it is non-streaming-only (`API_DOCUMENTATION.md:2456-2465`); this is not a persisted raw trace payload and cannot support a historical dashboard viewer.

**Severity.** **Critical.** The panel is unavailable as specified. A JSON view synthesized from the current trace row would be partial and should not be labeled a full trace.

**Change risk and cost.** Requires a new payload/event persistence contract or an archive pointer plus reader. It is not a pure additive field change because retention, encryption/access control, redaction, size limits, streaming semantics, and enterprise audit logging must be defined. The `trace:read_raw` authorization check can be added independently, but authorization alone cannot create missing data.

**Existing/deferred status.** The permission requirement is explicitly in the 4.D.2 milestone. The missing persistence contract is a new finding.

## Gap 8 — Cross-links are not all backed by exact per-request identifiers

**Evidence.** The UX requires links to memory details, the current directive diff, and session replay (`UI_UX_GUIDELINES.md:224-227`). The milestone describes those targets but provides no join contract (`4.d.2-trace-inspector.mdx:41-48`). Memory IDs are available for included memories (`context.proto:66-74`), and directive/session IDs exist in domain schemas. However, the context response lacks a request/trace ID, the trace row’s `checkpoint_id` is always nil because checkpoint append does not return IDs (`services/proxy/internal/http/trace/assemble.go:24-30`), and the applied checkpoint has no message content (`000010_create_sessions.up.sql:45-80`).

**Mismatch.** Memory-detail links can be built for selected IDs, subject to tenant authorization, but excluded candidates and the exact scoring snapshot are not available. Directive-diff links are not exact per request because the assembly request mapper does not pass the directive version ID (`chat_context_assemble.go:119-130`) and the trace row stores no directive ID/hash. Session replay has a target session ID in the trace row when durable, but no applied event/transcript source to render a full timeline.

**Severity.** **High.** At least one link can appear syntactically valid while leading to a current object rather than the exact version used by the trace.

**Change risk and cost.** Adding immutable snapshot IDs or version hashes to the trace/event envelope is additive-safe for new data. Reliable replay requires the session event/state migration described in Gap 5. Existing trace rows cannot be made exact where only a session ID survives.

**Existing/deferred status.** The session/checkpoint limitations are explicitly deferred in the schema documentation. The missing link-level contract is a new finding.

## Gap 9 — Fallback and absent-assembly states are not represented in the durable trace contract

**Evidence.** The proxy distinguishes “assembly not attempted” from attempted fallback and records fallback in response headers (`chat_context_assemble.go:29-40`, `150-164`). The API documents `X-IBEX-Context-Fallback` and `context_assembly_ms` in the response metadata (`API_DOCUMENTATION.md:2446-2465`). The canonical `llm_traces` row has no context-attempted, context-fallback, fallback-reason, or context-token field (`DATABASE_SCHEMA.md:1791-1819`).

**Mismatch.** Historical dashboard queries cannot distinguish memory disabled, nil context client, skipped memory, RPC failure, and empty assembled context from a successful zero-memory assembly. This affects the summary, context panel, and root-cause interpretation of “why did my agent do that?”

**Severity.** **Medium to high.** The request can still be listed, but the dashboard may attribute behavior to “no memories” when assembly was not attempted or failed open.

**Change risk and cost.** Additive-safe nullable/enum fields. Values are already computed in the proxy; no new algorithm is required. Historical backfill is unavailable.

**Existing/deferred status.** The response-path distinction exists in implementation, but its durable export is a new finding.

## Gap 10 — Track D drift alerts depend on a planned read model that is not specified at dashboard contract level

**Evidence.** `4.D.4` promises grouped drift alerts, severity, impacted agent/timeframe, top-three drifted features, full feature drift tables, acknowledgement/resolution actions, and baseline reset/pause controls (`4.d.4-drift-alerts-directive-management.mdx:33-52`). Its prerequisites are a behavioral fingerprint schema and directive versioning API (`:87-92`). The page calls these planning sketches rather than an implementation contract (`:26-30`, `56-68`).

**Mismatch.** The milestone does not identify the exact table/API fields for feature values, baseline windows, z-scores, alert identity, acknowledgment state, resolution notes, or agent pause authorization. Without those fields, a dashboard can be designed against names that are not guaranteed to exist or to share `org_id`, `agent_id`, and time-window keys with trace data.

**Severity.** **Medium now; high at implementation start.** This is not a 4.D.2 blocker if drift alerts are separate, but it is the same class of data-contract risk across Track D.

**Change risk and cost.** A versioned alert/read API can be additive. If behavioral fingerprints are already stored, exposing aggregates is cheap; otherwise a new computation and backfill policy is required. Pause and MFA actions additionally need explicit authorization and audit contracts.

**Existing/deferred status.** The milestone names the dependency but does not provide a complete contract. This is a newly identified Track D contract gap.

## Gap 11 — Track D cost/usage analytics names backing schemas but does not define a complete joinable read model

**Evidence.** `4.D.5` promises quota usage bars, model cost breakdown, budget alerts, per-agent soft/hard spend caps, usage charts, and latency histograms (`4.d.5-analytics-v2-cost-governance.mdx:33-50`). It claims `usage_counters`, `tier_limits`, and `billing_events` already exist but were never wired to UI (`:33-35`), and lists “usage counter API available” as a prerequisite (`:83-87`).

**Mismatch.** The milestone does not specify the exact columns/API fields, currency and price version, aggregation grain, attribution key, quota reset timezone, or shared trace/request key. In particular, a cost chart cannot safely attribute spend to a trace unless provider/model/token/cost inputs and the same organization/agent/request dimensions are defined together. The future/planning schema examples in `DATABASE_SCHEMA.md:1846-2040` are explicitly not all applied and should not be treated as a live dashboard contract.

**Severity.** **Medium.** It may not block 4.D.2, but it can produce inconsistent analytics and trace-to-cost links if implemented from planning sketches.

**Change risk and cost.** Additive read APIs and materialized views are generally safe. Correct historical cost may require price-versioned recomputation and backfill. Hard caps and agent pauses need a durable policy/action audit trail, not only a chart query.

**Existing/deferred status.** The milestone itself identifies the UI wiring as missing. The absence of a defined join and aggregation contract is a new finding.

## Correlation and join integrity across the request pipeline

The effective pipeline is only partially joined today:

| Pipeline hop | Identifier present | Evidence | Audit result |
|---|---|---|---|
| Proxy ingress | `X-Request-ID` / generated request ID; `X-Trace-ID`/OTEL trace context; agent ID; optional external session ID | Proxy README and middleware tests; response contract (`API_DOCUMENTATION.md:2413-2444`, `2456-2465`) | Present in process, but not all identifiers reach every downstream contract |
| Proxy to context gRPC | org ID, agent ID, model, query, recent messages; proto supports session/directive fields but mapper omits them | `chat_context_assemble.go:119-130`; `context.proto:21-31` | **Request/trace ID absent; session/directive propagation incomplete** |
| Context to memory service | Retrieval request carries org, agent, query, model, and messages; memory hits carry enough internal scoring inputs for interim scoring | `services/context/app/assemble.py:191-204`; `scoring.py:28-45` | Present for retrieval, but no durable request ID and not all score dimensions are exported |
| Context response to proxy | assembled text, tokens, included memories, metrics internally; response contract has no trace ID | `context.proto:43-74`; `assemble.py:178-188` | Data exists transiently but cannot be historically joined |
| Proxy to ClickHouse trace | `request_id`, org, agent, optional session, model/provider, token and proxy latency subset | `trace/assemble.go:24-45`; `DATABASE_SCHEMA.md:1791-1819` | Present for the base request, absent for assembly payload/stages |
| Proxy to Postgres checkpoint | request ID, session/turn, hashes, token/latency metadata | `checkpoint.go:29-42`; `000010_create_sessions.up.sql:45-80` | Request/session join exists, but content and checkpoint ID linkage are incomplete |
| MCP tool audit to ClickHouse | request ID, org, optional agent, tool name, latency, outcome | `audit.py:33-80` | Present only for emitted MCP audit events; no args, idempotency, session, trace, sequence, or result |
| Dashboard trace read | `request_id` can find the base trace row | `DATABASE_SCHEMA.md:1791-1819` | Cannot safely join assembly payload, raw JSON, full conversation, or exact directive snapshot |

The key distinction is between **request correlation** and **trace correlation**. `request_id` is sufficient to identify the base LLM trace row and is written to checkpoints and MCP metadata in some paths. `trace_id` is exposed in proxy metadata but is not a column in `llm_traces`, `mcp_tool_calls`, or the context proto. `span_id` is not present in the audited dashboard contracts. A robust design should choose one canonical immutable inference identifier and carry it through every assembly, memory, tool, checkpoint, raw-payload, and trace event, while retaining request/session IDs as secondary dimensions.

## Schema/proto evolution assessment

| Gap class | Additive-safe? | Needs migration/backfill? | Computation status |
|---|---|---|---|
| Context RPC `request_id`/`trace_id` | Yes, new proto fields | No migration for new rows; historical joins remain missing | Already available in proxy context; propagation only |
| Assembly stage metrics in ClickHouse | Yes, nullable/defaulted columns | Schema migration; no reliable historical backfill | Already computed by context service |
| Per-memory confidence/frequency/similarity/tokens/reasons | Yes, repeated-message additions | New payload only; no historical backfill | Mixed: some internal, some need candidate/packer instrumentation |
| Real memory composite score | Yes | No safe historical backfill | Memory service computes it; context currently uses interim score |
| Tool arguments/idempotency/sequence | Yes at table level | ClickHouse migration; no historical backfill | Idempotency exists in client path; args require capture/redaction |
| Full conversation/raw trace | Not just a field addition | New JSONB/event/archive store, retention and access migration | Content is currently intentionally not persisted |
| Directive hash and exact per-request version | Yes for new trace rows | Optional trace-column migration; no historical exactness | Hash computation is new; ID is available in domain data but not propagated |
| Session replay event stream | Schema-additive if `session_events` is introduced | Migration and writer/read API; historical replay unavailable | Current proxy writes checkpoint metadata only |
| Drift alert read model | Usually additive API/materialized view | Possible fingerprint backfill | Depends on Phase 4.5 schema not specified here |
| Cost/usage attribution | Additive API/view | Price-versioned backfill may be required | Token inputs exist; complete cost attribution contract is not defined |

Proto changes should follow the repository’s existing additive policy: reserve new field numbers, do not reuse removed fields, and deploy readers before relying on new writers. ClickHouse additions should be nullable or have safe defaults because old rows cannot contain the new values.

## Session and conversation-history determination

The current 4.D.2 source table leaves the conversation source undecided between MinIO and ClickHouse (`4.d.2-trace-inspector.mdx:43-47`). The audited live path does not support either option as a full transcript source:

1. `ibex.llm_traces` is metadata-only and explicitly omits prompt/completion content (`DATABASE_SCHEMA.md:1786-1819`).
2. The applied `ibex_core.checkpoints` table stores hashes and operational metadata, not `messages`, `completion`, or a JSON state (`000010_create_sessions.up.sql:45-80`).
3. The proxy checkpoint writer hashes the messages and completion before persistence (`checkpoint.go:29-58`).
4. The engineering schema’s richer `state JSONB`, `session_events`, and `archived_to` sections are documented but are not in the applied Phase-2 migration; the schema itself calls those fuller columns not yet migrated (`DATABASE_SCHEMA.md:780-783`, `892-979`).
5. No audited implementation establishes an operational MinIO writer/read path for trace conversation archives.

Therefore, the currently migrated session subset **does not support reconstructing a full conversation transcript**. It supports ordering and metadata for turns through `session_id`, `turn_index`, `request_id`, and `created_at`, but content reconstruction depends on a not-yet-migrated state/event/archive contract.

## Additional undocumented assumptions to resolve before 4.D.2

The following assumptions should be made explicit in the implementation contract:

1. **“Full trace payload” is not defined.** Specify whether it includes original request JSON, post-assembly messages, assembled context, provider request/response, tool arguments/results, memory candidates, and errors. Define redaction before storage, not only before display.
2. **Streaming is under-specified.** The embedded `ibex` metadata is omitted from streaming bodies (`API_DOCUMENTATION.md:2456-2465`), while the UX promises response content. Define whether streaming chunks are archived, summarized, or reconstructed from a final checkpoint.
3. **Retention differs by store.** `llm_traces` and `mcp_tool_calls` have 90-day TTLs (`DATABASE_SCHEMA.md:1815-1819`, `1839-1843`), while session and possible MinIO archives have no single trace-inspector retention contract. Cross-links can silently break after ClickHouse expiry.
4. **Tenant isolation must apply to every join.** `org_id` is present in primary tables, but a future payload/event store must enforce the same RLS or service-layer tenant checks. Memory IDs, directive IDs, request IDs, and session IDs must not be treated as globally sufficient authorization keys.
5. **Failure-path event identity is inconsistent.** The MCP auth rejection path creates a new random request ID (`middleware.py:151-165`) rather than necessarily retaining the originating request identity. The audit schema has no trace/session fields to repair this later.
6. **Checkpoint ID linkage is incomplete.** The trace writer currently sets `CheckpointID: nil` because append does not return IDs (`trace/assemble.go:24-30`). A dashboard cannot use checkpoint identity as a stable bridge until that write path is changed.
7. **Current versus historical directive content is ambiguous.** A directive diff target must point to immutable version content and preserve the version used at inference time, not query the agent’s current active directive.
8. **The 4.D.2 golden-trace test cannot be exact with current persistence.** The milestone requires a known input to produce an exact rendered summary (`4.d.2-trace-inspector.mdx:75-79`), but the required raw input, response, per-candidate decisions, and assembly stages are not all persisted.

## Prioritized implementation checklist

### Must fix before `4.D.2` implementation starts

1. **Define and propagate one canonical inference correlation ID.** Add `request_id` and preferably `trace_id` to the context assembly request/response path, carry them into memory retrieval/audit events, persist them in the trace payload, and document the dashboard join. This ranks above the other known gaps because all six sections depend on joining one request.
2. **Choose the durable conversation/raw-payload source.** Decide between an append-only Postgres event/state model, MinIO/object storage, or a dedicated trace payload store. Define sanitized versus privileged payloads, retention, encryption, RLS, `trace:read_raw`, enterprise view-audit events, streaming behavior, and tenant-scoped lookup keys. Without this, conversation and raw JSON cannot be implemented honestly.
3. **Make `ibex.llm_traces` or its companion read model carry assembly metrics.** Persist `context_assembly_ms`, context attempted/fallback/reason, context tokens, and the `AssemblyMetrics` stage fields or an immutable reference to them. These values are already computed, so this is a relatively cheap additive change, but it must be tied to the canonical inference ID.
4. **Resolve the score-contract naming and payload.** Do not expose the interim `0.85 × similarity + 0.15 × confidence` value as the memory-service composite. Add the real composite and the UX-required components, raw similarity, confidence, access frequency, per-memory tokens, candidate disposition, and exclusion reason to a versioned context trace payload. This builds directly on the known memory gap.
5. **Define the exact per-request directive snapshot.** Propagate directive version ID into assembly, persist its immutable hash/version reference with the inference, and specify the read contract for the directive diff link. This is required for explaining behavior and avoids linking to the wrong current version.
6. **Expand the tool-call audit contract.** Add sanitized arguments, idempotency key, session/trace/inference IDs, call sequence or precise start time, and a structured outcome reference. Use an additive ClickHouse migration as anticipated by the existing schema note. This builds directly on the known tool timeline gap.
7. **Update the golden-trace fixture contract after persistence decisions.** The fixture must assert the exact joinable summary, assembly stages, selected/excluded memories, conversation source, tool events, and raw JSON authorization state. Otherwise the milestone’s success test cannot detect the current data loss.

### Can ship as a degraded/partial view and fix later, if explicitly labeled

1. **Basic summary header.** Ship agent/session/model/provider, token totals, provider TTFB, directive latency, and total latency from `llm_traces`; label context-stage detail unavailable until the enriched trace contract lands. This incorporates the known latency-breakdown gap.
2. **Included-memory list only.** Show IDs, rank, category, and the currently available scores only if the interim-score naming is corrected; do not claim five-component memory-service scoring or exclusion reasoning.
3. **Metadata-only tool timeline.** Show tool name, latency, success, and error code while clearly omitting arguments and idempotency until the table expands. This is acceptable only as a documented degraded state.
4. **Session metadata link.** Link to session identity and turn metadata, but do not call it session replay or conversation view while the applied migration contains hashes only.
5. **Memory detail links.** Link selected memory IDs with tenant authorization, while documenting that the link is to the current memory record and not necessarily an immutable per-trace snapshot.
6. **Track D drift and analytics screens.** Do not implement against milestone prose alone. First publish versioned read contracts for fingerprint alerts, directive workflow state, usage counters, billing events, price versions, quota resets, and shared correlation dimensions. Their current planning status permits later contract work, but it should not be silently inferred from planning schema sketches.

## References

[1]: `web/engineering/UI_UX_GUIDELINES.md` "IBEX Harness UI/UX Guidelines"

[2]: `web/engineering/API_DOCUMENTATION.md` "IBEX Harness API Documentation"

[3]: `web/engineering/DATABASE_SCHEMA.md` "IBEX Harness Database Schema"

[4]: `web/content/roadmap/phase-4-multi-provider/milestones/4.d.2-trace-inspector.mdx` "Milestone 4.D.2 — Trace Inspector"

[5]: `packages/proto/proto/ibex/context/v1/context.proto` "ibex.context.v1 Context Assembly Proto"

[6]: `infra/migrations/postgres/000010_create_sessions.up.sql` "Applied Phase-2 Sessions and Checkpoints Migration"

[7]: `services/proxy/internal/http/chat_context_assemble.go` "Proxy Context Assembly Integration"

[8]: `services/proxy/internal/http/session/checkpoint.go` "Proxy Checkpoint Construction"

[9]: `services/proxy/internal/http/trace/assemble.go` "Proxy Trace Record Construction"

[10]: `packages/clickhouse/record.go` "ClickHouse Trace Record"

[11]: `services/context/app/assemble.py` "Context Assembly Orchestration"

[12]: `services/context/app/scoring.py` "Context Interim Scoring"

[13]: `services/context/app/packer.py` "Context Memory Packer"

[14]: `services/mcp-memory/app/audit.py` "MCP Tool-Call Audit Emitter"

[15]: `services/mcp-memory/app/middleware.py` "MCP Middleware Audit Failure Path"

[16]: `web/content/roadmap/phase-2-single-provider/milestones/2.4.1-sessions-checkpoints-migrations.mdx` "Milestone 2.4.1 — Session and Checkpoint Schema Migrations"

[17]: `web/content/roadmap/phase-4-multi-provider/milestones/4.d.3-memory-browser-v2-graph.mdx` "Milestone 4.D.3 — Memory Browser V2"

[18]: `web/content/roadmap/phase-4-multi-provider/milestones/4.d.4-drift-alerts-directive-management.mdx` "Milestone 4.D.4 — Drift Alerts and Directive Management"

[19]: `web/content/roadmap/phase-4-multi-provider/milestones/4.d.5-analytics-v2-cost-governance.mdx` "Milestone 4.D.5 — Analytics V2: Cost Governance"

[20]: `web/engineering/adr/0033-clickhouse-schema.mdx` "ADR-0033 ClickHouse Schema"

[21]: `web/content/docs/adr/0032-session-data-model.mdx` "ADR-0032 Session Data Model"

[22]: `web/content/docs/adr/0050-mcp-audit.mdx` "ADR-0050 MCP Audit"

[23]: `web/content/docs/adr/0069-memory-packing.mdx` "ADR-0069 Memory Packing"

[24]: `web/content/docs/adr/0071-context-assembly-orchestration.mdx` "ADR-0071 Context Assembly Orchestration"

[25]: `web/content/roadmap/phase-4-5-intelligence-layer/milestones/4.5.a.2-fingerprint-schema-migration.mdx` "Behavioral Fingerprint Schema Migration"
