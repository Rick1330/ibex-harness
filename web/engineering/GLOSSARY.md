# IBEX Harness — Glossary

This glossary enforces consistent language across:

- documentation,
- code,
- issues/PRs,
- and dashboards.

If a term is used in a PR or issue, it should match these definitions.

---

## Core Entities

### Agent

An “agent” is a configured AI system that:

- makes LLM calls through the IBEX Proxy,
- has persistent memory scoped to an organization,
- runs in sessions,
- and follows directives.

**Key fields:** agent_id, org_id, config, active_directive_version_id

---

### Organization (Org / Tenant)

A tenant boundary. All customer data is scoped to an organization.

**Invariant:** org A cannot see org B’s data, enforced by RLS and other layers.

---

### User

A human account that manages an org’s agents and data via the dashboard/API.

**Not the same as agent.** Users are operators; agents are compute identities.

---

### Session

A session is the unit of agent execution over time. It is used for:

- crash recovery,
- session replay in the dashboard,
- grouping traces,
- enforcing loop detection,
- tracking directive version in effect.

Sessions have a state machine:
`initializing → active → suspended → resuming → completed/failed/abandoned`

---

### Heartbeat

A periodic signal (typically every 10 seconds) indicating that an agent session is still alive.

**Used for:** detecting crashed agents and transitioning sessions to `suspended`.

---

### Checkpoint

An immutable snapshot of session state used for crash recovery.

Contains (typical):

- conversation history (possibly compressed)
- pending memory writes
- completed tool idempotency keys
- plan state / variables

Checkpoints are append-only and ordered by sequence_number.

---

### Session Replay

The ability to reconstruct a session timeline from event logs + checkpoints.

Used in the dashboard to answer:

- what happened at each turn?
- what memories were injected?
- what directive was active?
- what tool calls occurred?

---

## Memory System Terms

### Memory

A persistent unit of knowledge stored for future retrieval.

Memories include:

- content (text)
- embeddings (vector)
- category (factual/preference/behavioral/episodic/procedural)
- confidence score
- usefulness score (feedback-updated)
- visibility scope (agent/org/session)
- lifecycle status (active/superseded/archived/quarantined/deleted)

---

### Memory Category

A coarse classification of memory content:

- **Factual**: stable facts (“User’s DB is PostgreSQL”)
- **Preference**: preferences (“User prefers dark mode”)
- **Behavioral**: patterns (“User likes concise answers”)
- **Episodic**: events (“In session X we fixed bug Y”)
- **Procedural**: how-to (“To deploy, run steps A→B→C”)

**Note:** External integrations should default to factual unless reviewed.

---

### Memory Deduplication

The process of preventing duplicate memories from being stored.

Typical stages:

1. exact dedup: content hash match
2. near-duplicate: vector similarity threshold
3. semantic equivalence: deeper check (optional/expensive)

---

### Memory Conflict

A relationship between two memories that cannot both be true or should not both be active.

Common conflict types:

- contradiction (A vs not-A)
- overlap (same meaning)
- supersedes (new replaces old)
- specializes (new is a refinement)

---

### Quarantined Memory

A memory stored but excluded from automatic retrieval due to:

- PII detection, or
- prompt injection risk score exceeding threshold.

Requires human review to activate.

---

### Prompt Injection (Memory Context)

A class of attacks where untrusted text tries to manipulate the model’s instructions.

In IBEX, memory content is untrusted input and must be injected as data with strong delimiters.

---

## Context Assembly Terms

### Directive

The instruction set / system prompt that defines how an agent behaves.

Directives are versioned and promoted through a workflow.

---

### Directive Version

An immutable snapshot of directive content.

Version graph is like Git commits:

- parent version(s)
- version number
- status lifecycle (draft/review/active/deprecated/revoked)

---

### Regression Scenario

A test case for directive behavior defined as:

- input conversation (messages)
- expected behavior description (natural language)
- optional critical flag (failure blocks promotion)

Evaluated by a judge (LLM or deterministic rules where possible).

---

### Context Assembly

The process of constructing the final prompt context for an inference call.

Inputs:

- directive content
- recent conversation history
- relevant memories
- tool schemas (if applicable)

Constraints:

- token budget (model context window)
- latency budget (must not stall proxy)

---

### Token Budget

The maximum tokens allowed in an LLM context window, minus reserved space for response and safety buffer.

Budget allocation typically prioritizes:
directive → history → memories → tools.

---

### Memory Ranking

The algorithm that orders candidate memories for injection.

Typically composite score:
`0.40 relevance + 0.25 recency + 0.20 usefulness + 0.10 confidence + 0.05 frequency`

---

### “Lost in the middle”

A known attention pattern where LLMs attend most strongly to the start and end of the context window.
IBEX mitigates by ordering and packing context intentionally.

---

## Proxy / Tracing Terms

### LLM Proxy

The Go service that intercepts requests from agents to LLM providers.

Responsibilities:

- auth validation + caching
- rate limiting
- context injection
- streaming response forwarding
- trace emission
- async job triggering

---

### Provider Adapter

A module that translates internal normalized request/response structures to provider-specific formats (OpenAI/Anthropic/etc.)
This is how we handle provider API changes without rewriting the proxy.

---

### Trace

A record of an inference call with timing, token counts, provider metadata, and injected memory IDs.

Traces power:

- debugging (“why did agent do that?”)
- analytics dashboards
- billing event generation

---

### Span

A sub-unit of a trace in distributed tracing (OpenTelemetry).
Example spans: auth validation, rate limit check, context assembly, provider call.

---

## Worker / Reliability Terms

### At-least-once delivery

A queue guarantee: a job may run more than once, but it will run at least once.

Therefore tasks must be idempotent.

---

### Idempotency Key

A unique key that ensures an operation can be safely retried without duplicating effects.

Used for:

- memory writes
- tool calls in session recovery
- webhook deliveries
- billing event ingestion (dedup)

---

### DLQ (Dead Letter Queue)

A queue for jobs that repeatedly fail beyond retry limits.
DLQ depth is a critical alert signal.

---

### Circuit Breaker

A resilience mechanism:

- closed: requests pass
- open: requests fail fast (dependency unhealthy)
- half-open: probe dependency to see if it recovered

Used in proxy for providers and optionally internal service calls.

---

## Security / Compliance Terms

### RLS (Row-Level Security)

PostgreSQL feature that enforces row visibility based on session variables.
IBEX uses it for tenant isolation at the DB layer.

---

### Right to Erasure (GDPR)

Legal requirement to delete customer data upon request.
IBEX must:

- delete or redact data across storage layers,
- generate deletion certificates,
- and complete within defined SLA.

---

### BYOK (Bring Your Own Key)

A mode where customers provide their own LLM provider keys.
Keys must be encrypted at rest and never logged.

---

## Billing / Analytics Terms

### Billing Event

Append-only record of a billable action (tokens used, memory write/read, embeddings generated).
Stored in ClickHouse for auditability.

---

### Usage Counter

Near-real-time counters used to enforce quotas.
Typically stored in Redis and periodically persisted to PostgreSQL.

---

## “Don’t Confuse These” (Common Confusions)

- **User vs Agent**: user is human operator; agent is compute identity.
- **Directive vs Memory**: directive is instruction; memory is untrusted data.
- **Trace vs Log**: trace is structured causal record; log is message stream.
- **Checkpoint vs Replay**: checkpoint is snapshot; replay is reconstruction from events.
- **RLS vs org_id filter**: RLS is DB-level; org_id filter is defense-in-depth.
- **Auth vs AuthZ**: authentication is identity; authorization is permission.

---

If you add a new domain term, add it here before it becomes ambiguous in the codebase.
