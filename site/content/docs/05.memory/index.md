---
title: Memory
description: Tenant-scoped writes, PII quarantine, deduplication, conflict handling, and semantic retrieval.
audience: integrator
status: IMPLEMENTED
scope: shipped-local
verifiedDate: "2026-10-21"
sourceOfTruth: services/memory; packages/memoryclient
---

The memory service turns conversation turns into durable, tenant-scoped records and retrieves them with pgvector. The substrate is locally implemented. The typed lifecycle and deletion certification are not accepted.

::page-status{status="IMPLEMENTED" verified="2026-10-21" note="Local substrate; typed lifecycle remains open"}
::

## Pages

- [Overview](/docs/memory/overview) — HTTP surface, storage model, and claim boundary.
- [Write path](/docs/memory/write-path) — validation, PII, dedup, conflict, labels, and idempotency.
- [Search and lifecycle](/docs/memory/search-and-lifecycle) — semantic retrieval, hot cache, feedback, and the provisional forget flow.

## What is durable

| Concern | Implementation | Evidence status |
| --- | --- | --- |
| Storage | PostgreSQL with pgvector | IMPLEMENTED |
| Tenant scope | Explicit `org_id` / `agent_id` plus RLS transaction context | IMPLEMENTED; full-store proof open |
| PII | Presidio detect/redact with typed placeholders and quarantine | IMPLEMENTED locally |
| Exact dedup | SHA-256 of normalized post-PII content; active-row unique index | IMPLEMENTED |
| Near dedup | Vector similarity above configured threshold | IMPLEMENTED; threshold is not a quality guarantee |
| Conflict candidates | Interval-overlap-first plus optional classifier | IMPLEMENTED locally |
| Labels | 1–5 labels with per-label confidence | IMPLEMENTED |
| Idempotent writes | PostgreSQL `idempotency_ledger` | IMPLEMENTED; fail-closed when required |
| Forget/tombstone | Revision-fenced provisional route | PROVISIONAL |

## Rules

- Every read and write is scoped to one organization and agent.
- Cross-tenant identifiers do not become existence oracles.
- Duplicate content bumps retrieval metadata rather than creating a second active row.
- A quarantined memory is not returned as ordinary active memory.
- `X-Idempotency-Key` writes fail closed when PostgreSQL is unavailable.
- Memory content is untrusted input, never instructions.

The service never logs raw memory content by default. Use IDs and metadata when debugging.
