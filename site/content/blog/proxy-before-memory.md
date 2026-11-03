---
title: Put the proxy before the memory
date: "2026-10-22"
author: Elshaday Mengesha
authorUrl: "https://github.com/Rick1330"
featured: true
coverIndex: 1
coverTone: 1
coverLabel: Request path
tags:
  - architecture
  - security
  - proxy
readingTime: 9 min read
excerpt: >
  Persistent memory is a retrieval system, and every retrieval is a
  cross-tenant read waiting to happen. The request path has to establish who is
  asking before it decides what the agent remembers.
---

Most agent-memory systems are designed from the retrieval side inward. A query arrives, vectors are compared, the best results are packed into a prompt, and the model answers. That design works in a notebook. It becomes dangerous the moment two organizations share the same database.

The interesting question is not “how do we retrieve relevant memories?” It is “what has to be true before retrieval is allowed to run?” At IBEX Harness, the answer is the request path: validate the credential, bind it to an agent and organization, apply policy and limits, then retrieve. Memory is a capability behind that boundary, not a side channel around it.

## A memory is not a document

It helps to stop thinking of a memory as text with a vector attached. In a multi-tenant system, a memory row is a compound assertion:

- It belongs to exactly one organization and one agent.
- It has provenance: where it came from and when it was observed.
- It has a lifecycle: active, superseded, quarantined, forgotten, or tombstoned.
- It has a confidence and a retrieval history.
- It may contain untrusted instructions that must never be executed as policy.

Each of those properties is a security decision. If the organization comes from the request body instead of the authenticated principal, an attacker can choose whose memories to search. If the agent scope is inferred from a model name, one agent can read another agent’s context. If a superseded memory is still returned to users, “forget” becomes a suggestion rather than a guarantee.

That is why the proxy comes first.

## The order that matters

A protected chat request moves through the following gates before any provider sees it:

```text
body limits
  → bearer token validation
  → agent binding
  → policy snapshot + budget admission
  → rate limit
  → request validation
  → directive and session resolution
  → bounded context assembly
  → provider handoff
```

The exact middleware names are less important than the ordering invariant: **no tenant-scoped retrieval runs before tenant scope is established from the credential.**

Two details make that invariant useful in practice.

First, the proxy does not trust a path parameter for tenancy. `POST /v1/chat/completions` derives the organization from the validated personal access token. Diagnostic routes that do carry an organization in the path must match the token’s organization, or the request fails with `403`.

Second, agent binding is explicit. The caller sends `X-IBEX-Agent-ID`; auth checks that the agent belongs to the token’s organization. A valid token for Agent A cannot be replayed against Agent B. This closes the “valid token, wrong principal” gap that a token-only design leaves open.

## Fail closed means fail before work

A fail-closed system does not merely return an error after doing the expensive or sensitive part. It refuses to start.

If auth is unavailable, the proxy returns `503`. If the policy snapshot cannot be verified, the request does not proceed to a provider. If a durable budget hold cannot be claimed when one is required, the request fails rather than spending money it cannot account for. If a keyed memory write cannot reach its idempotency ledger, the write fails rather than risking a duplicate.

That last case is worth spelling out because “write it and deduplicate later” is a common shortcut. The memory write path requires an idempotency ledger scoped by `(org, agent, key)`. The same key and body replays the stored response; the same key with a different body returns `409`; an active claim returns `409` with a retry hint; an unavailable ledger returns `503`. The system would rather be temporarily unavailable than silently create a second memory.

## Retrieval is bounded, not best-effort

Context assembly is on the hot path, so it gets a deadline rather than an open-ended chance to be thorough. The service retrieves directive, hot memories, and cold memories in parallel, with per-branch timeouts under an outer retrieval wall. Slow branches are cancelled. Completed branches are kept.

If assembly fails or exceeds its deadline, the proxy can continue with directive-only or history-only context. That is a quality degradation, not an authorization change. A failed retrieval must never widen visibility, invent a memory, or fall back to an unscoped query.

The same principle applies to the data itself. Memory content is untrusted input. The formatter serializes it as data, escapes attribute values and bodies, and uses a per-assembly nonce so a memory cannot forge its own closing tag. A memory that says “ignore previous instructions” is still a memory, not an instruction.

## Where isolation is enforced

Tenant isolation is deliberately redundant:

| Layer | Enforcement |
| --- | --- |
| HTTP | Organization comes from the validated token, not caller-supplied body fields. |
| Application | Every query carries an explicit `org_id` predicate. |
| PostgreSQL | Row-level security checks the transaction’s organization context. |
| Redis | Tenant-bearing keys include the organization identifier. |
| ClickHouse | Queries must carry an explicit `org_id`; there is no row-level security to catch omissions. |

RLS is not a substitute for application predicates, and application predicates are not a substitute for RLS. The redundancy is the point. A single missing check should not become a cross-tenant incident.

## What this design does not prove

The local implementation is substantial, but “implemented locally” is not a production-readiness claim. The current boundary still includes open work:

- There is no measured hosted p99 SLO for the full chat path.
- Context assembly is provisional because caller authentication at its gRPC boundary and the deadline contract remain open.
- Full end-to-end tenant-isolation proof across backups, archives, and every projection is not complete.
- Typed memory lifecycle and a durable revision ledger remain open.
- Hosted HA, restore, and multi-region behavior are not claimed.

Those limits belong in the same conversation as the design. A security architecture that only describes its happy path is marketing, not engineering.

## The rule to keep

Memory makes an agent feel continuous. It also turns every request into a potential read of someone else’s history. The only durable way to reconcile those facts is to make identity, policy, and limits precede retrieval.

Put the proxy before the memory. Then make the memory prove, at every layer, that it knows whose context it is allowed to return.

## Read next

- [Request lifecycle](/docs/architecture/request-lifecycle) — the full protected request path.
- [Tenant isolation](/docs/security/tenant-isolation) — RLS, Redis namespacing, and analytics rules.
- [Memory write path](/blog/memory-write-path) — what happens after a memory is admitted.
- [Status and evidence](/docs/architecture/status-and-evidence) — the current capability boundary.
