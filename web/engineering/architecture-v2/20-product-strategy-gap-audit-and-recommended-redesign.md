# IBEX Harness: Product Strategy, Gap Audit, and Recommended Redesign

**Author:** Manus AI  
**Date:** 2026-10-02  
**Scope:** This document evaluates IBEX Harness as an agent-infrastructure product. It intentionally does not treat the current Console or dashboard implementation as the product’s primary differentiator. It covers the gateway, identity, policy, memory, context assembly, workers, MCP, evidence, deployment, and interoperability with existing agent frameworks and coding agents.

## The decision

IBEX should become the **self-hostable, multi-tenant agent control and context plane** that sits underneath existing agents.

It should provide a compatible model endpoint, governed memory and context, enforceable budgets, tenant-aware identity, MCP integrations, and durable evidence. It should not become another agent framework, another IDE, another generic provider catalog, another graph database product, or another hosted observability dashboard.

The product promise should be simple:

> **Change one base URL or add one MCP server. Keep the agent framework you already use. Gain hard tenant isolation, explainable policy, pre-call spend control, portable context, and evidence-grade operations.**

This is a stronger direction than the current broad interpretation of “harness.” The existing architecture already contains the ingredients: a Go proxy, AuthService, provider abstraction, tokenizer registry, memory service, context assembly, asynchronous workers, MCP memory tools, PostgreSQL/pgvector, Redis, ClickHouse, MinIO, protobuf, and OpenTelemetry.[1] [2]

The important change is not to add every adjacent feature. It is to make the product boundary explicit and make the guarantees real.

## What IBEX is for

IBEX is for organizations that already use agents but cannot safely operate them as isolated scripts and vendor-specific subscriptions.

The primary user is a platform, security, or infrastructure team supporting several agent applications. Those applications may use LangGraph, OpenAI Agents SDK, CrewAI, Microsoft Agent Framework, custom Python or TypeScript code, Claude Code, Codex, Cursor, GitHub Copilot, or a mixture of them.

That team has recurring problems:

- Provider credentials are scattered across applications and developers.
- Model names and capabilities differ between providers.
- Usage, retries, fallbacks, tool calls, embeddings, and context expansion create unpredictable cost.
- Framework-local memory is difficult to govern, migrate, inspect, and delete.
- A valid token is often treated as if it grants access to every agent or tenant resource.
- Prompt files, memory, MCP results, and repository content are mixed with instructions.
- Hosted agent products do not all allow a transparent gateway in their request path.
- Observability is often delayed, vendor-specific, or unsafe to export.
- Operators need to understand not just what the model returned, but why it was allowed, which context it received, how much it cost, and which policy version made the decision.

IBEX should solve those problems without requiring the organization to rewrite its orchestration code.

It is not primarily for a hobbyist who only wants to call one model, a team seeking the largest provider catalog, or a buyer looking for a visual multi-agent builder. Those users already have simpler options. A direct SDK, LiteLLM, a hosted gateway, LangGraph, Letta, Mem0, or a coding-agent product may be the better choice.[3] [4] [5]

## The correct product shape

IBEX should be organized around four planes.

### 1. Enforcement plane

This is the Go hot path. It authenticates the caller, verifies the agent and resource scope, checks policy and capabilities, reserves budget, applies rate and concurrency limits, selects a provider deployment, forwards the request, and returns a compatible response.

The enforcement plane must remain small and predictable. It should not become the place where every memory extraction, graph query, evaluation, or dashboard feature runs.

The current architecture’s intended behavior is directionally right: authentication and tenant isolation fail closed, while context and memory dependencies may degrade to a safe lower-quality response. The documented proxy target is less than 20 ms of added p99 overhead, but this remains a target until measured by published benchmarks.[1]

### 2. Context plane

This contains memory, session state, retrieval, directives, context assembly, provenance, and safety handling.

The context plane must distinguish several things that competing products often collapse into one “memory” feature:

- Ordered conversation or session history.
- Framework checkpoints and resumable run state.
- Durable semantic memories and facts.
- Project or repository context.
- Immutable directives and policy.
- Retrieved external documents and tool results.
- Prompt templates and their versions.

These data classes have different owners, lifetimes, mutation rules, trust levels, and token budgets. A LangGraph checkpoint is not semantic memory. A `CLAUDE.md` file is not an authorization policy. A model-generated fact is not equivalent to a user-confirmed fact. A tool result is not a trusted instruction.

IBEX should make those distinctions visible in its API and data model.

### 3. Evidence plane

This is the durable record of what happened: admission decisions, identity, policy versions, reservations, provider attempts, raw and normalized usage, memory candidates, context decisions, tool calls, approvals, retries, fallbacks, errors, and artifacts.

The existing combination of OpenTelemetry, Prometheus, ClickHouse, and an evidence outbox is suitable, but the current project must not call asynchronous logging “evidence-grade audit” until it has durable delivery, replay, deduplication, retention, and restore guarantees.[2]

OpenTelemetry should remain the portable export protocol. ClickHouse should be the queryable analytics and evidence store. Postgres should remain authoritative for policy, identity, configuration, and lifecycle state. Object storage should hold larger or sensitive payloads only under explicit retention and redaction policy.

### 4. Operations plane

This includes management APIs, key lifecycle, policy promotion and rollback, readiness, migrations, backup and restore, operator diagnostics, deployment profiles, and release compatibility.

The operations plane is not a cosmetic dashboard. It is part of the trust contract. A self-hosted customer must be able to determine whether a budget is hard or degraded, whether an event was persisted, whether a migration is safe, whether a memory deletion propagated, and which provider capability caused a request to fail.

The repository currently describes Phase 4 operator readiness as in progress and labels several operator and UI surfaces provisional.[1] That is not a criticism of the direction. It means product claims must be gated by demonstrated readiness rather than by the presence of service directories or diagrams.

## Why the current broad idea would fail

The broad version of IBEX contains several valuable products at once: model gateway, memory system, context compiler, agent runtime, MCP server, observability backend, operator console, prompt manager, graph layer, guardrail engine, and potentially coding-agent platform.

That breadth creates three risks.

First, adoption becomes unclear. Users do not know whether they should install IBEX for the proxy, memory, governance, MCP, or agent execution. The first successful experience becomes too complex.

Second, the compatibility surface grows faster than the team can test it. Every provider and framework has different behavior for streaming, tools, structured output, reasoning, continuation, embeddings, usage, retries, and error formats. A long provider list is not the same as semantic compatibility.

Third, operational responsibility expands faster than the product’s safety evidence. A platform storing prompts and memory, enforcing budgets, and publishing audit records carries much higher trust requirements than a simple vector database or stateless proxy.

The answer is not to abandon the architecture. The answer is to make the core narrow and the extensions explicit.

## Competitive conclusion

IBEX cannot beat the strongest adjacent products by copying their breadth.

### LiteLLM

LiteLLM’s adoption engine is an OpenAI-compatible gateway, virtual keys, model aliases, teams, budgets, rate limits, provider routing, fallbacks, a large provider catalog, and easy Docker deployment. It has the clearest generic gateway wedge.[3]

IBEX should not compete on provider count. It should either route through LiteLLM as an upstream or allow LiteLLM to sit behind IBEX for long-tail provider support.

IBEX can differentiate on:

- Stronger tenant and agent identity semantics.
- Atomic, fail-closed budget admission rather than post-call spend reporting.
- Memory and context as first-class, permissioned data domains.
- Provenance, supersession, quarantine, and freshness.
- Evidence that explains why a request was allowed and what context was used.
- A typed Go contract with provider capability discovery and strict unsupported-feature errors.

LiteLLM’s documented DB-less mode is useful for quickstarts but cannot enforce global budgets without authoritative state. Public issue history also shows why budget behavior, malformed streaming, provider regressions, configuration drift, and supply-chain safety must be tested rather than assumed.[3]

### Portkey and Prisma AIRS

Portkey focuses on a universal gateway with fallbacks, routing, guardrails, caching, MCP, and provider integrations. Prisma AIRS extends the security story across LLM, MCP, and A2A interactions.[4]

IBEX should integrate with such systems. A customer may use Prisma for specialized threat detection or Portkey for routing while using IBEX for self-hosted identity, durable memory, context assembly, and evidence.

IBEX should own the parts that must remain close to customer data and authorization. It should not attempt to reproduce a security vendor’s threat-intelligence platform.

### Helicone and Langfuse

Helicone demonstrates the power of an OpenAI-compatible gateway plus immediate request visibility. Langfuse demonstrates how tracing can become the entry point for prompt management, evaluation, datasets, and production feedback.[5] [6]

Both should be treated as complements. IBEX should export high-quality OTLP and provide Langfuse-compatible integration rather than rebuilding every evaluation and dashboard feature.

The difference is enforcement. Helicone and Langfuse primarily help teams understand what happened. IBEX must also decide whether the request is permitted, reserve cost before provider execution, decide which memory is eligible, and fail closed when authorization or billing integrity cannot be established.

### Mem0

Mem0 has a much better memory activation path than IBEX currently has: a short `add`/`search` loop, Python and TypeScript packages, REST, CLI, MCP, framework adapters, and a hosted/self-hosted ladder.[7]

IBEX should copy its simplicity, not its entire product surface.

The missing differentiation is governed memory. IBEX should provide mandatory tenant and agent scopes, append-only observations, active-state projections, provenance, valid intervals, supersession, quarantine, redaction, feedback, job status, and deletion propagation.

A production memory system cannot treat every extracted sentence as a current truth. Public user reports around memory systems show recurring problems with junk capture, repeated system text, stale facts, contradictory facts, hidden extraction failures, and leaked sensitive content.[7]

### Zep and Graphiti

Zep and Graphiti are stronger when temporal facts, entities, relationships, and source lineage are central. Graphiti’s temporal model preserves episodes and represents when a fact was valid separately from when it was recorded.[8]

IBEX should not make a graph database a default dependency. It should first implement temporal lineage over PostgreSQL and only add a graph accelerator if measured workloads prove that graph expansion materially improves retrieval quality for a defined class of queries.

The important lesson is not “build a graph.” It is “preserve source events, temporal validity, provenance, and supersession.”

### Letta

Letta owns a different layer: the stateful agent runtime. Its product unit is an agent with conversations, memory, tools, and resumable execution. Its adoption is driven by a working agent experience and transparent state, not by a standalone vector API.[9]

IBEX should integrate with Letta rather than clone Letta Code, MemFS, skills, or its runtime loop.

The useful IBEX role is to provide a tenant-scoped memory and policy backend, a provider gateway, cost controls, OTel evidence, MCP tools, and durable export. Letta can continue to own agent behavior and execution.

### LangGraph and LangChain

LangGraph’s durable execution contract is valuable: threads, checkpoints, runs, interrupts, human approval, streaming, and resumability. LangChain supplies higher-level model, tool, middleware, and agent abstractions.[10]

IBEX should preserve existing LangGraph code. The integration should be a model client, Store adapter, optional checkpoint adapter, trace bridge, and policy layer. IBEX should not create a competing graph DSL.

The distinction between a checkpointer and a semantic Store is especially important. Short-term graph state and long-term governed memory should have separate schemas, retention, deletion, and security policies.

### CrewAI, AutoGen, and Microsoft Agent Framework

CrewAI is opinionated and approachable. AutoGen is more composable and message-oriented, although its repository now directs new users toward Microsoft Agent Framework and describes AutoGen as maintenance mode.[11]

The correct IBEX integration is thin:

- A model client or OpenAI-compatible endpoint.
- A memory protocol adapter.
- MCP configuration.
- OTel propagation.
- External budgets and run limits.
- Tenant identity that does not rely on framework-local metadata.

IBEX should pin supported versions and publish compatibility tests. Framework memory should be treated as a cache or view, not the canonical multi-tenant memory ledger.

### OpenAI Agents SDK and Responses

The OpenAI Agents SDK has a strong code-first adoption path: `Agent`, `Runner`, function tools, handoffs, agents-as-tools, MCP, guardrails, sessions, and tracing. Responses is the lower-level stateful item API.[12]

IBEX should not reproduce the Runner. It should support the seams:

- OpenAI-compatible Chat Completions.
- A lossless Responses-compatible path.
- Session persistence.
- A tracing processor that exports to OTel and ClickHouse.
- MCP policy and memory tools.
- Provider and budget controls.

Flattening Responses items into Chat Completions messages would break continuation, tool discovery, MCP call items, response IDs, streaming order, and replay. Responses must be treated as a separate contract with capability flags.

### Claude Code, Codex, Cursor, and GitHub Copilot

Coding agents are an important distribution channel, but they are not a single technical integration.

Claude Code explicitly supports custom gateways and proxy variables, so a direct IBEX gateway path is plausible.[13] Codex supports configuration files and MCP, including remote Streamable HTTP. Cursor and Copilot provide MCP, repository integrations, actions, webhooks, Apps, and hosted execution surfaces, but parts of their cloud execution may be outside a customer-controlled LLM request path.[14] [15]

IBEX must state this boundary honestly. It cannot promise to transparently govern every request made by every hosted coding agent.

The integration strategy should be:

- Use the gateway where the agent supports a custom base URL or BYOK path.
- Use MCP for memory, policy queries, run status, approvals, and trace lookup.
- Use GitHub Apps, Actions, webhooks, or supported APIs for Copilot and repository workflows.
- Use OTel or native exporter paths where available.
- Provide configuration snippets and a diagnostic command for each product.

The strongest unserved use case is not “replace Claude Code” or “replace Cursor.” It is **govern several different coding agents while preserving one identity, memory, policy, cost, and evidence model**.

## The core product wedge

The first product should be a hardened compatibility wedge:

1. A tested OpenAI-compatible Chat Completions endpoint.
2. A tested Responses subset that preserves item semantics.
3. Server-side provider credentials and model aliases.
4. Explicit principal identity: organization, subject, agent, project or repository, session, run, trace, and scopes.
5. Pre-call token and dollar reservation.
6. Rate limits, concurrency caps, provider circuit breakers, and bounded fallbacks.
7. One Streamable HTTP MCP server for governed memory and context.
8. One memory round trip with provenance and safe retrieval.
9. One evidence event that is durable, queryable, and linked to the request.
10. Copy-paste examples for OpenAI SDK, OpenAI Agents, Codex, Claude Code, LangGraph, CrewAI, AutoGen, and generic MCP clients.

The first user should be able to run Compose, change `base_url`, supply an IBEX token, make one request, write one memory, search it, and see the decision trace.

They should not need to understand the full internal topology before obtaining value.

## Canonical identity and request contract

IBEX needs a canonical signed principal and run envelope. Every request should resolve to something like:

```text
Principal:
  org_id
  subject_id
  subject_type: user | service | agent
  agent_id
  project_id / repository_id
  session_id
  run_id
  trace_id
  policy_version
  scopes
  auth_source
  data_classification
  idempotency_key
```

Some fields may be absent for a simple proxy call, but the system should not silently invent security identity from arbitrary caller headers.

`X-IBEX-Agent-ID` can identify the requested agent, but AuthService must verify that the token owns or may use that agent. A caller-supplied scope is a filter request, not authority.

The principal must flow through:

- Proxy to provider.
- Proxy to context assembly.
- Memory service and embedder.
- MCP server and tool calls.
- Worker jobs.
- OTel spans.
- ClickHouse evidence.
- Object storage artifacts.
- Exporters and webhooks.

A valid bearer token must never imply access to every organization resource. The project’s security rules already require explicit permission, role, and resource checks, plus PostgreSQL RLS, application-level `org_id` predicates, Redis namespacing, and ClickHouse query guards.[2]

## Budget enforcement must become a first-class subsystem

A budget shown after the response is not enforcement.

IBEX should introduce an **Admission → Reservation → Execution → Reconciliation** lifecycle.

### Admission

Before provider work, estimate:

- Current input tokens.
- Retrieved context tokens.
- Maximum output tokens.
- Reasoning or hidden-token reserve where applicable.
- Retry and fallback reserve.
- Tool and MCP call reserve.
- Embedding and extraction reserve for memory operations.
- Maximum number of agent turns or steps.

The estimate should use the capability and tokenizer registry. Unknown prices must be explicit. A request should not silently receive a zero-cost estimate because the model catalog is stale.

### Reservation

Reserve the estimated amount atomically at the relevant scopes:

- Organization.
- Project or repository.
- Agent.
- User or service identity.
- API key.
- Run or session.

Redis is suitable for the low-latency counter and lease path. PostgreSQL should remain authoritative for durable policy and configuration. The reservation needs a unique ID and an idempotency key.

### Execution

The proxy must enforce the reservation. It should cap output, tool calls, retries, fallback depth, wall time, and concurrency. It should return machine-readable metadata such as:

```json
{
  "budget_enforcement_mode": "enforced",
  "reservation_id": "...",
  "estimated_cost_usd": 0.012,
  "policy_version": "...",
  "remaining_budget_usd": 12.44
}
```

A real implementation should use valid UUID values rather than the illustrative placeholders above.

### Reconciliation

After the provider returns, record raw usage and normalize it. Reconcile the reservation with actual input, output, cached, reasoning, tool, and retry usage. Record refunds or additional debits as append-only events.

Every allow, deny, reservation failure, provider attempt, fallback, refund, and degraded decision should be represented in evidence.

If Redis or the authoritative policy store is unavailable, billing-sensitive enforcement should fail closed. A separate explicitly named availability mode may exist for non-billing contexts, but it must expose a degraded state and never be the default production behavior.

This is a major opportunity because public gateway incidents show that concurrent checks and store failures can overspend even when a configuration flag claims fail-closed enforcement.[3]

## Provider compatibility is a contract, not a model list

The provider registry should expose capabilities per deployment, not only a model name.

At minimum, each route should declare whether it supports:

- Chat Completions.
- Responses.
- Anthropic Messages.
- Streaming.
- Tool calls.
- Structured output.
- Reasoning fields.
- Continuation or previous-response IDs.
- Background execution.
- Usage reporting.
- Tokenizer family.
- Context window.
- Price source and freshness.
- Retry semantics.
- Data residency or region.

A public alias such as `fast-code` must be separate from the provider deployment identity. The alias is stable for clients. The deployment identity is operational and may change during routing.

Every request should be able to explain which alias, policy, provider, deployment, capability decision, retry, and fallback chain were used.

The release gate must include official-client and adversarial tests for:

- Non-streaming responses.
- Streaming chunks and termination.
- Malformed upstream chunks.
- Tool calls and tool results.
- Structured outputs.
- Refusals and errors.
- Usage metadata.
- Multimodal inputs where supported.
- Response continuation.
- Provider timeouts and partial output.
- Cross-tenant authorization.

A malformed response from one provider must not crash the entire proxy process.

## Governed memory: the part that can become a moat

IBEX should not claim that its extractor is smarter than Mem0, Zep, or another memory engine without representative evaluations. It can win by making memory safer, more explainable, and more portable.

### Separate observations from current state

Store raw or normalized observations in an append-only history. Build a current-state projection from those observations.

A memory fact should carry:

- `org_id`.
- `agent_id`, `user_id`, project, repository, and session scope as applicable.
- Source event or span ID.
- Source class: user-confirmed, user-provided, agent-inferred, imported, tool-derived, or system-generated.
- Observed-at time.
- Processed-at time.
- Valid-from and valid-to when meaningful.
- Confidence.
- Status: active, superseded, merged, archived, expired, quarantined, or deleted.
- Content hash.
- Embedding profile and version.
- Actor that created or changed it.
- Retention and legal-hold state.
- Supersedes and superseded-by links.

The default retrieval view should exclude inactive, expired, quarantined, and superseded facts. History must remain available for audits and explicit time-travel queries.

### Make writes idempotent and observable

Memory writes that involve extraction or embedding should return a durable operation ID. The caller should be able to query pending, running, succeeded, and failed states.

The operation needs a content hash and idempotency key. At-least-once workers must produce exactly-once effects at the memory projection boundary.

Read-after-write semantics must be explicit. A caller should know whether a successful write is immediately searchable, cached, queued, or awaiting embedding.

### Keep expensive work off the proxy path

The Go proxy may retrieve from Redis hot cache and use bounded context assembly. Extraction, embeddings, PII deep scans, conflict resolution, reranking, consolidation, and graph expansion should run asynchronously unless a specific policy requires synchronous enforcement.

If memory is unavailable, IBEX may fall back to directive-only context or a safe hot cache. It must never widen visibility, bypass organization checks, or inject unverified content because a dependency is unavailable.

### Treat memory as untrusted data

The repository’s security model is correct to require nonce-delimited, escaped memory injection and to treat stored text as untrusted prompt context.[2]

That rule must extend to:

- MCP results.
- Repository instructions.
- GitHub issues and comments.
- Slack messages.
- External documents.
- A2A artifacts.
- Tool descriptions.
- Agent-authored files.
- Imported memories.

Policy must be outside the retrieved text. The model can suggest a memory write, but it cannot grant itself permission to write across scopes, call a protected tool, or change an authorization policy.

### Memory feedback and correction are product features

A user or operator must be able to:

- See why a memory was retrieved.
- See its source and freshness.
- Mark it useful or wrong.
- Correct it.
- Supersede it.
- Quarantine it.
- Delete it and verify deletion propagation.
- Export it before migration.

This is more important than adding graph traversal prematurely.

## Context assembly should be a bounded compiler

Context assembly should receive a verified principal and policy. It should return both the assembled context and a manifest.

The manifest should include:

- Directive version.
- Included memory IDs.
- Excluded memory IDs and reasons where safe.
- Visibility filters applied.
- Retrieval scores or score components.
- Freshness and confidence.
- Token counts by category.
- Model and tokenizer identity.
- Cache hit or miss.
- Degradation flags.
- PII or quarantine decisions.
- Injection wrapper version.

The current architecture’s short context deadline and directive-only fallback are sound design choices.[1]

The important improvement is to make the result explainable and testable. A context compiler should behave predictably under budget pressure. It should not silently wipe context because token counting failed or because a model uses a different tokenizer.

Every assembled context should have a maximum size, a model-aware packing strategy, and a clear fallback reason.

## MCP should be the first interoperability product

MCP is already supported by Claude Code, Cursor, LangChain, GitHub Copilot, and many other clients. It is therefore a better distribution mechanism than writing a deep plugin for every framework.[16]

The first IBEX MCP server should expose a narrow set of stable tools:

- `memory.search`.
- `memory.get_provenance`.
- `memory.write_candidate`.
- `memory.feedback`.
- `memory.review` where operator permission exists.
- `context.preview`.
- `budget.status`.
- `trace.get` with tenant-safe scope.

Do not mirror every REST route into an MCP tool. Large catalogs reduce selection accuracy and consume context. GitHub’s own documentation recommends limiting toolsets for this reason.[15]

Every tool should have:

- A stable version.
- A narrow JSON schema.
- Pagination and output limits.
- An explicit read or write classification.
- A scope derived from the authenticated principal.
- An idempotency key for writes.
- A timeout and cancellation behavior.
- An audit event.
- A policy decision.
- A tool-definition hash or version.

The current MCP service should be treated as a resource server, not an OAuth identity provider. Integrate an existing IdP or gateway for OAuth authorization-server behavior. Document the difference between a PAT, service token, and user OAuth token.

Provide both remote Streamable HTTP and a local stdio option, but hard-disable stdio in production profiles unless explicitly enabled. Add an `ibex mcp doctor` command that checks:

- URL and TLS.
- Metadata discovery.
- Auth and scopes.
- Tool list and version.
- Startup time.
- Request latency.
- Timeouts.
- Common 401, 403, and 404 failures.
- Output size limits.
- Tenant and agent mapping.

MCP tool descriptions and results are untrusted input. Tool poisoning and rug-pull behavior are documented risks in the ecosystem.[16] IBEX should pin or hash tool definitions where possible, show effective inputs, support allowlists, and require approval for sensitive writes.

## A2A should be later and narrower

A2A is useful for agent-to-agent tasks, but it is not the right first product. It introduces Agent Cards, task lifecycle, artifacts, streaming, push notifications, multiple bindings, and authentication patterns.[16]

IBEX should eventually expose an A2A edge adapter that maps an authenticated task to an existing durable worker job. It should not create a new agent runtime or share internal memory automatically.

The initial subset should be:

- An explicit Agent Card.
- Authenticated send.
- Get task.
- Cancel task.
- One tested streaming or polling path.
- Durable task IDs mapped to existing run IDs.
- Artifact references that are expiring and tenant-bound.
- Conformance tests using the A2A TCK.

A2A’s design is specifically intended to allow collaboration without exposing internal state. IBEX should preserve that property.

## Integrating with existing frameworks

The integration model should be additive. The customer keeps the framework’s graph, agents, tools, and loop.

### LangGraph and LangChain

Provide:

- An OpenAI-compatible model client.
- A LangGraph Store adapter backed by IBEX memory.
- An optional checkpointer adapter only after the run contract is stable.
- SSE and run correlation.
- OTel spans for thread, run, node, tool, checkpoint, and memory operations.
- Durable approval and interrupt mapping where useful.

Map a framework `thread_id` into a tenant-scoped composite. Never treat a bare thread ID as globally addressable.

Keep checkpointer state separate from semantic memory.

### OpenAI Agents SDK

Provide:

- An OpenAI-compatible Responses endpoint.
- A Session implementation over tenant-scoped persistence.
- An OTel `TracingProcessor` bridge.
- MCP policy and memory examples.
- Usage and budget propagation.
- A documented distinction between `handoff` and `as_tool`.

Do not implement a second Runner.

### CrewAI

Provide a tested `LLM` configuration and memory/storage adapter. Make hidden extraction opt-in rather than silently creating model calls. Map CrewAI’s memory scope and feedback fields into canonical IBEX fields.

### AutoGen and Microsoft Agent Framework

Provide a model client, Memory protocol adapter, MCP configuration, and OTel bridge. Do not depend on Studio’s local persistence as the canonical source of truth.

### Letta

Provide import/export and a memory adapter. Map Letta agent, user, conversation, and run identities to IBEX principal fields. Support portable blocks or archived context without claiming that IBEX is the Letta runtime.

### Mem0

Provide a compatibility layer for add, search, get, update, delete, history, and event status. Document semantic differences clearly. Allow users to migrate into IBEX’s richer current-state and provenance model.

### Langfuse and LiteLLM

Provide a Langfuse OTLP/export profile and a LiteLLM upstream route. These integrations reduce adoption resistance and make IBEX useful without requiring a replacement architecture.

## Coding-agent adoption

The best coding-agent integration is not a replacement CLI. It is a policy and context layer that improves the tools developers already use.

IBEX should provide official recipes for:

- Claude Code custom gateway and MCP.
- Codex `config.toml` and MCP.
- Cursor project/team MCP.
- GitHub Copilot repository MCP and Actions/webhooks.
- Generic OpenAI SDK and Anthropic-compatible clients.

The principal for a coding-agent run should include:

```text
org_id
user_id
agent_id
repository_id
installation_id
branch_or_worktree
session_id
run_id
trace_id
policy_version
```

Repository instruction files such as `CLAUDE.md`, `AGENTS.md`, and Cursor rules should be imported as context with source and commit provenance. They must not become hidden authorization policy.

The evidence record should include:

- Budget admission and estimate.
- Model/provider and actual usage.
- MCP tools discovered and called.
- Approval decisions.
- Commands and tests where an integration exposes them.
- Artifact, commit, or pull request references.
- Retry and fallback chain.
- Memory sources and context token counts.
- Policy decisions.

The north-star outcome is not generated lines of code. It is cost per accepted change, test-pass rate, review rework, rollback rate, time to useful PR, and policy incidents prevented.

## Packaging and deployment

IBEX should have explicit deployment profiles.

### Development profile

One Compose command should start enough to demonstrate:

- Authenticated model request.
- Provider forwarding.
- One memory write.
- One memory search.
- One evidence event.

PostgreSQL and Redis should be included. Embeddings, ClickHouse, and MinIO may be optional or use development-safe defaults.

### Single-node self-hosted profile

This should include pinned images, migrations, readiness, management API, proxy, workers, Postgres/pgvector, Redis, optional ClickHouse and MinIO, backup/restore documentation, and rollback guidance.

The profile must never silently advertise hard budgets when it is missing the state required to enforce them.

### HA production profile

This should document independently scalable proxy/AuthService, context and workers, Postgres, Redis/Valkey, ClickHouse, MinIO/S3, OTel Collector, external secrets, immutable image digests, SBOM/provenance, migration preflight, graceful drain, and support windows.

### Standalone profiles

A proxy-only package can be useful, but its limits must be explicit. It should not claim memory, tenant-wide budgets, or durable evidence if those dependencies are absent.

A memory-context profile and an evidence profile can be independently useful when they share contracts and security middleware.

Managed hosting should come later, after self-hosted backup, upgrade, isolation, and evidence behavior is proven. The cloud version should not create an extreme OSS-versus-hosted feature cliff.

## What must be redesigned or made explicit

### Keep

- Go proxy and AuthService boundary.
- Provider abstraction.
- Tokenizer registry.
- Context assembly as a bounded service.
- PostgreSQL/pgvector memory substrate.
- Redis hot cache and rate limiting.
- Python workers for expensive asynchronous work.
- MCP as an external integration boundary.
- OTel and Prometheus.
- Defense-in-depth tenancy.
- Fail-closed authentication and rate controls.
- Fail-open quality degradation for optional memory/context dependencies.

### Redesign

- Turn budgets into atomic reservations and reconciliation.
- Turn audit into a durable outbox with replay and deduplication.
- Add capability flags to provider deployments.
- Separate public model aliases from provider identities.
- Separate memory observations from active projections.
- Add embedding-profile versioning and migration.
- Add durable memory operation IDs and status.
- Make context manifests and degradation reasons observable.
- Add per-agent MCP rate and concurrency limits.
- Add MCP tool-definition versions or hashes.
- Introduce a canonical principal/run envelope.
- Publish OpenAPI, protobuf, and generated SDK contracts.
- Add recovery, backup, restore, migration, and rollback acceptance tests.
- Label every feature as shipped, provisional, specified, or deferred.

### Stop or defer

Stop competing on:

- Provider count.
- Generic routing cleverness.
- Broad dashboard parity.
- IDE or coding-agent UX.
- A graph database as the default memory architecture.
- A proprietary agent DSL.
- A global MCP marketplace.
- A universal agent runtime.
- A broad guardrail catalog before the hook contract is stable.

Defer A2A federation, temporal graph acceleration, advanced caching, a full coding sandbox, rich prompt-management UI, and managed cloud until the core contract has real design-partner evidence.

## Phased roadmap

### 0–3 months: prove the wedge

Ship:

- One-command Compose.
- Stable Chat Completions path.
- A tested Responses subset.
- Scoped keys and agent verification.
- Capability-aware aliases.
- Atomic preflight reservation MVP.
- Narrow Streamable HTTP MCP server.
- MCP doctor.
- One memory round trip with provenance.
- Durable evidence outbox MVP.
- Python and TypeScript examples.
- Configuration recipes for major frameworks and coding agents.
- Compatibility and security matrix.

The acceptance demo should be reproducible by a new user without reading the entire architecture.

### 3–6 months: make the guarantees credible

Ship:

- Complete Responses continuation, streaming, tool, and usage semantics for the supported subset.
- Anthropic compatibility where promised.
- Budget concurrency and store-failure tests.
- Evidence replay and deduplication.
- Redacted OTel and ClickHouse records.
- Policy promotion and rollback.
- Active/history memory projections.
- Provenance, supersession, quarantine, and status APIs.
- Signed images and SBOMs.
- Helm and backup/restore tests.
- LangGraph Store adapter.
- OpenAI Session and tracing adapters.
- CrewAI and AutoGen adapters.
- Langfuse exporter.
- LiteLLM upstream integration.

### 6–12 months: operate in real organizations

Ship:

- HA deployment profile.
- Migration and drain behavior.
- Durable runs and approvals where design partners need them.
- Cost-aware fallback.
- Guardrail hook contract.
- DLP or Prisma adapter.
- Repository and coding-agent identity.
- MCP OAuth deployment guidance.
- Retention, legal hold, export, and deletion propagation.
- Supported framework/version matrix.
- Policy explainability.

### 12–24 months: extend only from evidence

Consider:

- Managed regional/BYOK deployment.
- A2A edge adapter.
- Temporal lineage worker.
- Optional graph accelerator.
- Advanced cache and reranking.
- Richer GitHub integrations.
- Immutable directive registry.
- Private MCP registry metadata.

Every new service should beat the PostgreSQL/Redis baseline on a defined workload and have recovery evidence before it becomes a core dependency.

## Metrics that should decide the roadmap

The north-star metric should be:

> **Percentage of governed agent runs completed with an explainable, tenant-correct decision record and no policy, budget, or evidence-integrity violation.**

Track activation:

- Time to first successful request.
- Time to first memory round trip.
- Time to first evidence link.
- Setup completion without support.
- Retained deployments.
- Frameworks connected per deployment.

Track control quality:

- Budget overrun prevention.
- Estimate-versus-actual error.
- Reservation failure behavior.
- Decision latency.
- Visible retry and fallback rates.
- High-risk action denial rate.
- Cross-tenant findings, which must remain zero.

Track reliability:

- Proxy and context p95/p99.
- Stream crash containment.
- Provider outage recovery.
- Store-degradation behavior.
- Evidence loss, replay, and deduplication.
- Run resume success.
- MCP timeout and cancellation success.
- Backup, restore, and migration success.

Track memory quality:

- Useful-retrieval precision.
- Stale/conflicting fact exclusion.
- Provenance completeness.
- Correction rate.
- Quarantine quality.
- Read-after-write success.
- Context tokens saved.
- Cost per useful memory operation.

Track business value for coding agents:

- Cost per accepted change.
- Test-pass rate.
- Review rework.
- Rollback rate.
- Time to useful PR.
- Budget incidents prevented.
- Policy incidents prevented.

Do not use GitHub stars, number of providers, number of tools, or generated lines of code as the main product metrics.

## Final recommendation

The strongest concept is not “IBEX does everything around agents.” It is:

> **IBEX is the neutral, self-hostable enforcement and context plane for organizations running multiple AI agents.**

It sits at the seams where existing agent products are weakest:

- Before provider execution, it can enforce identity, budgets, model policy, and rate limits.
- During context assembly, it can provide permissioned, provenance-bearing, token-aware memory.
- At the tool boundary, it can govern MCP calls and preserve approvals and audit evidence.
- After execution, it can reconcile usage, record retries and outcomes, and export portable telemetry.

This product can be useful independently in several ways:

- A provider gateway without memory.
- A governed memory and context service without proxy routing.
- An MCP memory server for coding agents.
- An OTel/evidence sink.
- A policy and budget layer under a framework.

The services should be independently useful, but they must share one identity, policy, event, and compatibility model. That is the platform advantage.

IBEX wins when a team can keep its preferred agent framework and still obtain one trustworthy place for tenant identity, provider access, memory, cost, policy, and evidence. It loses if it asks users to replace LangGraph, Letta, CrewAI, OpenAI Agents, Claude Code, Cursor, or Copilot without offering a materially better workflow.

The strategic priority is therefore **compatibility plus correctness**. Build fewer surfaces, test them more deeply, and make every security, budget, memory, and evidence claim demonstrable.

## Skills, tools, rules, and execution control plane

The broader research identified a major missing layer in the original strategy: IBEX must govern not only model calls and memory, but the complete lifecycle of **skills, tools, rules, credentials, approvals, workspaces, artifacts, runs, and execution environments**. These are the control surfaces through which agents actually cause useful—and potentially harmful—effects.

### The fundamental boundary

> **Model-visible text can propose, explain, or inform. It cannot grant permission, widen tenant scope, mint credentials, or authorize side effects.**

This rule separates the context plane from the control plane:

- Skills, repository rules, memory, retrieved documents, attachments, tool descriptions, and tool results are context or data.
- AuthService, policy, capability grants, approvals, sandbox admission, and side-effect executors are authority.
- The Go proxy and enforcement edge must make the final allow/deny decision at each actual action boundary.

### Skills are governed packages, not permissions

Portable skills are converging around a directory with `SKILL.md`, concise metadata, and optional scripts, references, and assets.[26] [27] [28] This is a strong adoption pattern because it is easy to author and version-control, but skills may also contain executable code, MCP references, external URLs, dependencies, and malicious instructions.

IBEX should support standard `SKILL.md` and client-specific skill adapters while owning a tenant-scoped registry and resolver. Every skill version should have an immutable content digest, source commit, publisher, license, compatibility, declared resources/scripts, required capabilities, owner, evaluation status, and revocation state. Store immutable bundles in MinIO and lifecycle/ACL metadata in Postgres.

Use a four-stage loader:

1. Advertise filtered name/description metadata.
2. Load the skill body only after activation and policy checks.
3. Authorize each referenced resource read.
4. Run scripts only in a sandboxed worker with bounded filesystem, network, secret, CPU, memory, and output permissions.

The first product tier should be instruction-only skills. Shell, network, MCP, secret, and write capabilities need explicit declarations and stronger review. Skill metadata such as `allowed-tools` may inform review or client behavior, but it must never grant authorization.

### Tool calls need a provider-neutral contract

OpenAI, Anthropic, and MCP share the basic tool loop: define a named tool and schema, let the model propose a call, execute it outside the model, and return a correlated result.[29] [30] [31] IBEX should normalize this into protobuf-backed `ToolDescriptor`, `ToolCall`, and `ToolResult` contracts while preserving provider-specific adapters.

A `ToolDescriptor` should include a qualified tool ID, immutable version, descriptor digest, publisher/provenance, input and output schemas, side-effect class, required scopes, allowed resource selectors, data classification, timeout, idempotency support, and confirmation policy. A `ToolCall` must include tenant, actor, session, run, trace, exact `ToolRef`, canonicalized arguments, argument hash, policy snapshot, approval reference, idempotency key, deadline, and attempt. A `ToolResult` must distinguish success, denial, timeout, cancellation, retryable failure, and ambiguous/partial outcomes.

Registry search may discover candidates, but only AuthService/policy can make a candidate callable. Dispatch must use an exact ID/version/digest, never a display name or `latest` alias. Tool descriptions, annotations, schemas, arguments, and results are untrusted data. Tool poisoning research demonstrates why descriptor changes must trigger re-review and why a registry listing must not itself become permission.[32]

### Rules and instructions are context, not enforcement

`CLAUDE.md`, `AGENTS.md`, Cursor rules, Copilot instructions, and similar files are useful for project conventions and workflow guidance, but their scopes and precedence differ across clients.[33] [34] [35] IBEX should normalize them into a versioned `InstructionEnvelope` containing authority, scope, trust, source URI, content hash, tenant/project ownership, expiry, classification, and conflict status.

The canonical authority lattice should be:

```text
IBEX tenancy and hard safety constraints
  > tenant policy and AuthService decisions
  > approved DeploymentSnapshot
  > project/repository guidance
  > user task request
  > stylistic guideline
```

Repository files, issue text, pull requests, web pages, memory, and generated tool output must remain advisory or untrusted. They cannot weaken a higher-level deny, change tenant scope, or add a capability. IBEX should emit a loaded-instructions manifest showing included, omitted, conflicting, and superseded sources.

OPA or Cedar can be integrated as policy decision engines, but the application must enforce their structured decisions; model prose must never be the policy enforcement layer.[36] [37]

### Approvals are not sandboxes

Claude Code, Codex, OpenAI Agents, LangGraph, Cursor, and VS Code demonstrate a useful separation between technically enforced capability boundaries and approval policy.[38] [39] [40] Approval is a human or policy decision; it does not replace OS, filesystem, network, credential, or tenant isolation.

IBEX should separate capabilities from approvals. A capability is a narrow, short-lived grant for an action/resource/data class. An approval authorizes one exact canonical action or a tightly bounded homogeneous set. Bind it to tenant, run, policy version, resource version, exact normalized arguments, action digest, data destination, expiry, reviewer, and idempotency key. Re-check all of these immediately before the side effect. Edited approvals create a new action digest and require re-evaluation.

Use risk tiers instead of a global “auto” switch: read-only, workspace-write, guarded-write, auto-review inside a sandbox, and explicitly isolated full-access. Cross-tenant access, secret exfiltration, policy mutation, sandbox escape, and disallowed egress are unconditional denies. Approval fatigue is an adoption and security problem, so low-risk work should be automatically allowed only inside a technically enforced narrow boundary.

### Execution must be isolated from the control plane

IBEX should never execute model-generated shell or arbitrary plugin code inside Go proxy, AuthService, MCP memory, Postgres, Redis, ClickHouse, or MinIO processes. An execution worker should receive a signed, immutable `ExecutionPolicy` containing tenant/run identity, image or VM digest, read/write roots, network/DNS policy, quotas, timeout, secret grants, artifact limits, and approval/elevation state.

Use rootless OCI with namespaces, cgroups, dropped capabilities, `no-new-privileges`, seccomp, and MAC profiles for lower-risk work; use gVisor or Firecracker for hostile or cross-tenant workloads.[41] [42] [43] Network must be deny-by-default and enforced outside the worker through a host-side egress broker. Block private, link-local, metadata, and control-plane destinations. Do not allow automatic unsandboxed retries.

Secrets should be issued just in time, scoped to tenant/run/audience/action, and never placed in model context, ordinary logs, OTel attributes, memory, or snapshots. SPIFFE-style workload identity and Vault/KMS-backed credential brokering are suitable integrations.[44] [45] [46] [47]

### Runs, workspaces, and artifacts need one identity model

A live HTTP connection is not a durable job. OpenAI Background Responses, LangGraph, Letta, and Temporal all demonstrate the need for persisted state, event history, cursors, cancellation, retries, and idempotency.[48] [49] [50]

Add canonical contracts for `RunEnvelope`, `RunEvent`, `CheckpointEnvelope`, `OperationIntent`, `OperationReceipt`, `WorkspaceRef`, `ArtifactEnvelope`, and `PatchBundle`. Every retry is a new attempt under one logical run; every resume references a checkpoint; every fork creates a new run with an explicit parent checkpoint. Every external side effect creates an operation intent before execution and a receipt afterward. Ambiguous outcomes must be reconciled by operation ID, not blindly retried.

Use Postgres for authoritative run state, leases, fencing epochs, checkpoints, idempotency, and outbox rows. Use MinIO for immutable large artifacts, manifests, and snapshots. Redis is only a queue/lock/cache accelerator. ClickHouse and OTel are projections and evidence, not recovery truth.

Represent workspaces and artifacts by content digests, not paths or names. A `WorkspaceRef` should include the resolved base commit/tree, current snapshot, worktree ID, dirty/untracked state, environment image, and lease. A `PatchBundle` must specify the base snapshot and per-file preconditions; a textual diff is only a transport view. Git’s content-addressed blobs/trees and mutable refs provide the right conceptual model.[51]

### Context is an economic and security budget

Tool definitions, messages, tool results, attachments, retrieved documents, reasoning, and output share the effective context budget.[52] Deferred tool search exists because large catalogs degrade selection and consume substantial context.[53]

Make `ContextEnvelope` a typed, deterministic policy result. Each item carries tenant, source, trust/taint, provenance, sensitivity, expiry, byte/token estimates, tokenizer/model, and content hash. Reserve output/reasoning headroom first, then allocate budgets for policy, stable instructions, active skill, tool schemas, conversation, summaries, memory, retrieval, attachments, and tool results.

Use reference-first results, bounded continuation handles, authorization-before-ranking retrieval, and cache keys containing tenant, policy epoch, model, tokenizer, schema, and skill versions. Compaction must create a new lineage-bearing artifact rather than silently erase evidence. Never drop current constraints, policy, approval state, or evidence needed to explain a decision.

### Registry, plugins, and governance

Plugins and integrations are an adoption engine but also a supply-chain boundary. Claude Code, Cursor, VS Code, MCP, LangChain, CrewAI, and OpenAI Agents demonstrate the value of package ecosystems.[54]

IBEX should own a private self-hostable registry overlay that separates discovery, scanning, review, tenant enablement, runtime authorization, deprecation, and revocation. Require immutable digests, signatures or provenance, SBOMs, source commits, owners, compatibility matrices, declared capabilities, and staged rollout. A marketplace badge must not imply runtime trust.

Use lifecycle states such as draft, submitted, scanned, reviewed, approved, published, tenant-enabled, canary, active, deprecated, suspended, revoked, and archived. High-risk changes require proposer/approver separation. Exceptions are scoped, reasoned, expiring bindings—not edits to global policy.

### Evaluation must include actual effects

A plausible final answer is insufficient. Agent evaluation should include traces, tool trajectories, environment outcomes, repeated trials, deterministic graders, model graders, and human review.[55] [56]

Pin an immutable `DeploymentSnapshot` containing policy, skills, tools, model/provider, sandbox image, memory/retrieval state, schemas, and evaluator versions. Evaluate schema/protocol compatibility, tenant invariants, tool scope and arguments, actual storage/workspace state, side-effect absence after denial, sandbox isolation, citation support, cost/latency tails, recovery, and evidence completeness. Any auth bypass, tenant leak, forbidden side effect, sandbox escape, stale approval, or missing evidence is a hard release blocker regardless of aggregate quality.

### New canonical control-plane model

`DeploymentSnapshot` should become the unit of promotion and execution. It immutably references approved skill/tool/plugin digests, policy bundle hash, model/provider configuration, schema hashes, connector and credential policy, sandbox image or VM digest, context rules, dependency lock, evaluation evidence, and rollout/expiry metadata. A `RunManifest` derives from it and adds tenant, principal, workspace, input artifacts, memory/retrieval snapshot IDs, and trace identity.

The recommended control-plane contracts are:

```text
PrincipalContext, PolicyBundle, PolicyDecision,
SkillDescriptor, SkillVersion, ToolDescriptor, PluginDescriptor,
CapabilityManifest, InstructionEnvelope, ContextEnvelope,
ApprovalRequest, ApprovalGrant, ExecutionPolicy,
DeploymentSnapshot, RunEnvelope, RunEvent, CheckpointEnvelope,
OperationIntent, OperationReceipt, WorkspaceRef, ArtifactEnvelope,
PatchBundle, EvalRun, ProvenanceAttestation
```

### Revised roadmap additions

- **Phase 0:** freeze authority, principal, trust/taint, digest, lifecycle, and protobuf contracts; add adversarial golden fixtures.
- **Phase 1:** ship approved instruction-only skills and read-only tools with registry, manifests, tenant-scoped evidence, and no implicit invocation for untrusted packages.
- **Phase 2:** normalize tool calls and durable runs; add exact descriptors, approvals, idempotency, leases, checkpoints, artifacts, and private registry overlays.
- **Phase 3:** add rootless execution, host-enforced egress, credential brokering, workspace overlays, artifact scanning, cleanup, and Firecracker/gVisor options.
- **Phase 4:** add deterministic context economics, attachment handling, memory taint/ACLs, compaction lineage, cache isolation, and adapters for Claude, Codex, OpenHands, Cursor, Copilot, and AGENTS.md.
- **Phase 5:** add signed DeploymentSnapshots, provenance, staged rollout, lifecycle enforcement, deterministic replay, sandbox evidence, citation grading, and policy shadow/warn/deny modes.

The product should measure time-to-first-approved-tool, pinned/attested artifact percentage, skill activation accuracy, false-deny rate, approval fatigue, duplicate side effects, sandbox escape and egress attempts, run recovery, context cost, evidence completeness, rollback time, and revocation time—not provider count, package count, or average answer quality alone.

## References

[1]: https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/ARCHITECTURE.md "IBEX Harness system architecture and roadmap"
[2]: https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/SECURITY.md "IBEX Harness security model and mandatory controls"
[3]: https://docs.litellm.ai/docs/proxy/multi_tenant_architecture "LiteLLM multi-tenant architecture and budgets"
[4]: https://docs.portkey.ai/docs/product/ai-gateway "Portkey AI Gateway overview"
[5]: https://docs.helicone.ai/gateway/overview "Helicone AI Gateway overview"
[6]: https://langfuse.com/docs/observability/overview "Langfuse observability overview"
[7]: https://docs.mem0.ai/open-source/overview "Mem0 open-source overview and deployment model"
[8]: https://help.getzep.com/graph-overview "Zep temporal graph and context overview"
[9]: https://docs.letta.com/v1-sdk/concepts/stateful-agents/ "Letta stateful agents and durable agent state"
[10]: https://docs.langchain.com/oss/python/langgraph/persistence "LangGraph persistence, checkpoints, and Store concepts"
[11]: https://microsoft.github.io/autogen/stable/ "Microsoft AutoGen documentation and lifecycle"
[12]: https://openai.github.io/openai-agents-python/ "OpenAI Agents SDK documentation"
[13]: https://code.claude.com/docs/en/third-party-integrations "Claude Code third-party integrations and gateway configuration"
[14]: https://developers.openai.com/codex/mcp "OpenAI Codex MCP configuration and integration"
[15]: https://docs.github.com/en/copilot/concepts/context/mcp "GitHub Copilot MCP context and tool configuration"
[16]: https://modelcontextprotocol.io/specification/2026-07-28 "Model Context Protocol specification"

[26]: https://agentskills.io/specification "Agent Skills specification"
[27]: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview "Anthropic Agent Skills overview"
[28]: https://developers.openai.com/codex/skills "OpenAI Codex skills"
[29]: https://developers.openai.com/api/docs/guides/function-calling "OpenAI function calling"
[30]: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/handle-tool-calls "Anthropic tool-call handling"
[31]: https://modelcontextprotocol.io/specification/2025-06-18/server/tools "MCP tools specification"
[32]: https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks "MCP tool-poisoning security research"
[33]: https://code.claude.com/docs/en/memory "Claude Code memory and CLAUDE.md"
[34]: https://cursor.com/docs/rules "Cursor rules"
[35]: https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot "GitHub Copilot repository instructions"
[36]: https://www.openpolicyagent.org/docs "Open Policy Agent documentation"
[37]: https://docs.cedarpolicy.com/ "Cedar authorization documentation"
[38]: https://developers.openai.com/codex/agent-approvals-security "OpenAI Codex approvals and security"
[39]: https://openai.github.io/openai-agents-python/human_in_the_loop/ "OpenAI Agents SDK human-in-the-loop"
[40]: https://docs.langchain.com/oss/python/langchain/human-in-the-loop "LangChain human-in-the-loop middleware"
[41]: https://docs.docker.com/engine/security/ "Docker Engine security"
[42]: https://gvisor.dev/docs/ "gVisor documentation"
[43]: https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md "Firecracker design and isolation"
[44]: https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/authorization "MCP authorization tutorial"
[45]: https://datatracker.ietf.org/doc/html/rfc8707 "OAuth 2.0 Resource Indicators"
[46]: https://spiffe.io/docs/latest/spiffe-about/overview/ "SPIFFE workload identity"
[47]: https://developer.hashicorp.com/vault/docs/concepts/lease "Vault leases and dynamic secrets"
[48]: https://developers.openai.com/api/docs/guides/background "OpenAI background mode"
[49]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph interrupts"
[50]: https://docs.temporal.io/workflow-execution "Temporal workflow execution"
[51]: https://git-scm.com/book/en/v2/Git-Internals-Git-Objects "Git content-addressed objects"
[52]: https://platform.claude.com/docs/en/build-with-claude/context-windows "Claude context windows"
[53]: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool "Anthropic tool search"
[54]: https://code.claude.com/docs/en/plugins/overview "Claude Code plugins"
[55]: https://developers.openai.com/api/docs/guides/agent-evals "OpenAI agent evaluations"
[56]: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents "Anthropic agent evaluations"
