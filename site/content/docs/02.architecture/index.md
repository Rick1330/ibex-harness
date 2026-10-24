---
title: Architecture
description: How the services, data stores, trust boundaries, and request path fit together.
audience: architect
status: PROVISIONAL
scope: provisional
verifiedDate: "2026-10-21"
sourceOfTruth: engineering/architecture-v2/00-status-and-evidence.md; services/*/README.md
---

IBEX Harness is a set of independently deployable services around one authenticated request path and one tenant-scoped data plane. This section explains the design without turning the roadmap into a claim.

::page-status{status="PROVISIONAL" verified="2026-10-21" note="Go request path is implemented locally; Python and operator surfaces are mixed"}
::

## Read in this order

| Page | What it answers |
| --- | --- |
| [Overview](/docs/architecture/overview) | What are the major components and where does trust change? |
| [Services](/docs/architecture/services) | Which process owns which responsibility, and what is its status? |
| [Request lifecycle](/docs/architecture/request-lifecycle) | What happens between an inbound request and a provider response? |
| [Data model](/docs/architecture/data-model) | Which entities are tenant-scoped, and where do they live? |
| [Target architecture](/docs/architecture/target-architecture) | What are the target planes, authority boundaries, and ownership rules? |
| [Status and evidence](/docs/architecture/status-and-evidence) | What is actually evidenced, and what remains open? |

## Design principles

- **Identity is resolved at the edge.** The proxy never accepts an `org_id` from a client body or query string.
- **Tenant scope is explicit at every layer.** RLS is defense in depth, not a substitute for `org_id` predicates.
- **The critical path degrades.** Memory and context failures must not block inference; auth and admission failures deny the request.
- **Evidence is a product surface.** Status, limitations, and verification dates are part of the documentation, not release-note garnish.
- **The system is not declared production-ready by architecture alone.** Recovery, isolation proof, and hosted measurements are separate gates.

## Current topology

```mermaid
flowchart TB
  subgraph Edge
    Proxy["Go proxy"]
    API["Python management API"]
    Console["Next.js Console"]
  end
  subgraph Identity
    Auth["Go auth"]
    PG[("PostgreSQL + pgvector")]
  end
  subgraph Memory
    Memory["Python memory"]
    Context["Python context"]
    Embedder["Python embedder"]
    Worker["Celery workers"]
  end
  subgraph Evidence
    Redis[("Redis")]
    CH[("ClickHouse")]
    Relay["Go relay"]
  end
  Proxy --> Auth
  Proxy --> Redis
  Proxy --> PG
  Proxy --> Context
  Context --> Memory
  Memory --> PG
  Memory --> Embedder
  Worker --> Memory
  API --> Auth
  API --> PG
  Console --> API
  Relay --> PG
  Relay --> CH
```

The diagram is topology, not a deployment guarantee. The Helm chart is not deployable as committed; see [Kubernetes](/docs/deployment/kubernetes).
