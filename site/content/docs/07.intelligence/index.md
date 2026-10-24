---
title: Intelligence
description: Asynchronous workers, extraction, embeddings, deletion orchestration, and billing rollups.
audience: operator
status: PROVISIONAL
scope: provisional
verifiedDate: "2026-10-21"
sourceOfTruth: services/worker; services/embedder; engineering/architecture-v2/18-gap-register.md
---

The intelligence layer runs work that must not block the proxy: session extraction, memory writes, embeddings, organization deletion, billing reconciliation, maintenance, and MCP audit fan-out.

::page-status{status="PROVISIONAL" verified="2026-10-21" note="Several tasks are implemented; queue durability and exactly-once projection are not certified"}
::

## Pages

- [Workers](/docs/intelligence/workers) — queues, task families, dead letters, and enqueue admission.
- [Extraction](/docs/intelligence/extraction) — provider adapters, quality evaluation, and manual vLLM limits.
- [Embedder](/docs/intelligence/embedder) — CPU stub, TEI, hosted backends, and readiness geometry.
- [Extraction evaluation](/docs/intelligence/evaluation) — gold set, cassette replay, contract gates, and regression limits.

## What is implemented

| Capability | Status | Boundary |
| --- | --- | --- |
| Session extraction and memory writes | IMPLEMENTED | Cassette and unit evidence; live vLLM is manual |
| OpenAI and vLLM extraction providers | IMPLEMENTED | vLLM has no CI GPU runner |
| Embedding profiles (`cpu`, `gpu`, `hosted`) | IMPLEMENTED | CPU stub is not a quality model |
| Organization deletion orchestration | IMPLEMENTED | Full deletion certification remains open |
| Billing reconciliation and rollups | IMPLEMENTED | Hosted reconciliation evidence open |
| Dead-letter persistence, metrics, OTel | IMPLEMENTED | Alert rules exist; runbook practice is separate |
| Scheduled maintenance sweep | DEFERRED | Registered as a no-op, not business logic |

## Queue layout

| Queue | Purpose | Priority |
| --- | --- | --- |
| `extraction` | Session turns to memories | First |
| `embedding` | Async vector work | Second |
| `maintenance` | Beat sweeps and housekeeping | Third |
| `mcp_audit` | MCP tool-call audit fan-out | Last |

Redis DB allocation is deliberate: cache `0`, Celery broker `1`, rate limiting `2`, results `3`. Do not collapse them into one database.

## Non-negotiable boundary

A queued task is not a completed effect. Extraction can be retried, enqueue can be idempotent, and dead letters can be persisted, but the system does not currently claim exactly-once projection into every downstream store. Read [Evidence and relay](/docs/operations/evidence-and-relay) before treating an async side effect as durable.
