# Operator Platform Architecture

## Purpose

This document is the implementation companion for Phase 4 Tracks P, D, and E. It defines the contracts that make the operator dashboard trustworthy rather than merely attractive. The dashboard is a consumer of authenticated, versioned, tenant-scoped evidence; it is not the source of truth for traces, decisions, usage, or deletion.

## Product boundary

IBEX should be differentiated as an **auditable context-and-policy provenance debugger**. The core workflow starts in global Explore and traverses a session, trace, checkpoint, retrieval candidate, memory score vector, context pack, directive version, routing decision, tool call, provider fallback, evaluation, incident, and rollout record. Every conclusion must link to immutable source evidence or be labeled unknown.

## Contract layers

| Layer | Required contract | Primary store or transport |
|---|---|---|
| Identity | operator session, tenant membership, permission, assurance, revocation | API/auth service |
| Evidence | trace/span/event IDs, parent/links, sequence, operation kind, status, provenance | OTel-compatible envelope, ClickHouse projection, object manifest |
| Publication | event identity, aggregate sequence, schema version, digest, delivery state | Postgres transactional outbox, Redis relay |
| Governance | capture mode, redaction, retention, deletion, legal hold, audit | Postgres policy and audit records, encrypted object storage |
| Query | typed filters, facets, cursors, freshness, completeness, URL state | API query contract and bounded analytical projections |
| Control | action intent, approval, before/after, idempotency, rollback | Postgres operator-action ledger |
| Assurance | fixture, environment, commit, image, schema, result, artifact | CI/staging evidence bundle |

## Mandatory identifiers

`trace_id` identifies distributed causality. `session_id` identifies a conversation or application grouping. `checkpoint_id` identifies the persisted turn snapshot. `span_id` and `parent_span_id` identify operation hierarchy. `event_id` identifies one immutable event. `aggregate_seq` gives deterministic ordering within an aggregate. These identifiers must not be inferred from timestamps or content hashes.

## Data lifecycle

Content capture defaults to metadata-only. Redacted or privileged content is captured only under a versioned policy and is stored with an encrypted manifest, digest, retention class, and deletion state. ClickHouse TTL is storage hygiene; it is not the application deletion SLA. Organization and data-subject deletion must propagate through Postgres, ClickHouse, Redis, object storage, queues, exports, and derived projections, and must return a verifiable receipt.

## Publication and replay

Business changes and their outbox event are committed atomically. Relays are at-least-once and therefore idempotent. Downstream consumers acknowledge only after durable write. Replay starts from an outbox position or immutable evidence manifest, not from an expiring Redis stream. Partial, sampled, redacted, late, and deleted evidence must be represented explicitly.

## Security boundary

The server evaluates tenant and resource authorization on every request. Raw payload access, export, deletion, replay, policy change, secret use, and break-glass require separate permissions and recent authentication assurance. Dashboard rendering treats prompts, tool arguments, outputs, links, HTML, and Markdown as untrusted inert data. Provider secrets and bearer tokens are never displayed.

## Release boundary

A capability is promotable only when Track P gates, capability tests, accessibility tests, performance budgets, recovery evidence, supply-chain verification, and rollback procedures pass. Dark launch and staged rollout are required for new policy, routing, cost, and replay behavior.

## Required evidence

Each milestone record must link to contract snapshots, golden fixtures, tenant-negative tests, redaction/deletion results, performance data, CI reports, deployment digests, restore-drill output, and rollback transcripts.

## Trace Inspector data prerequisites

The Trace Inspector (4.D.2) is honest only when the evidence plane exposes the following join keys and payloads. Missing fields must surface as `unknown` or `not evaluated`, never as zero or empty.

| Field / artifact | Source | Consumer |
|---|---|---|
| `trace_id`, `span_id`, `parent_span_id`, `aggregate_seq` | Proxy, context assembly, workers | Span tree, ordering |
| `session_id`, `checkpoint_id`, `turn_id`, `request_id` | Session/checkpoint writes | Session bridge, turn replay |
| `AssemblyMetrics` (stage timings) | Context assembly | Run summary strip |
| Retrieval candidate list with retrieval rank, metric similarity, final rank, `delta_rank` | Context assembly scorer | Candidate matrix |
| Composite score components and weights (`0.40/0.25/0.20/0.10/0.05`) | Versioned score payload | Explain tree |
| Exclusion reason (`budget`, `filter`, `failed`, `unknown`) | Packer/scorer | Exclusion groups |
| Directive snapshot hash/version | Policy store at inference time | Provenance panel |
| Tool audit (sanitized args, idempotency key) | MCP/tool path | Tool span detail |

## Publication topology

```text
Write path:  business txn + outbox row (same Postgres txn)
Relay:       at-least-once, idempotent by event_id + aggregate_seq
Projections: ClickHouse (analytics), read models (API), object manifest (raw)
Replay:      from outbox position or immutable manifest — not Redis TTL alone
```

Partial, sampled, redacted, late, and deleted states are first-class on every read API and SSE envelope.

## Operator action ledger

High-impact actions (export, deletion, replay, policy change, fallback override, break-glass raw read) share one ledger shape:

- `action_id`, idempotency key, actor, assurance level, resource scope
- `preview_hash` / dry-run result before commit
- `before_hash`, `after_hash`, approval context (when required)
- `rollback_pointer` to prior config/version/digest
- immutable audit event linked to `trace_id` where applicable

Counterfactuals and replay are **simulated** against immutable snapshots; they never mutate the observed production trace.

## Deployment and recovery

Operator topology requires committed K8s/Helm/Kustomize overlays (4.P.5), dependency-aware readiness (not startup-only), drain for SSE, and documented RPO/RTO. Restore drills must verify tenant isolation post-restore. Image promotion uses immutable digests with SBOM/provenance and admission verification.

## Research provenance

Staff-engineering audits that informed this architecture are archived under [research/operator-platform/](research/operator-platform/README.md). Published roadmap and engineering pages supersede the archive.
