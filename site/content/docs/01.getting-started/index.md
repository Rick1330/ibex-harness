---
title: Getting started
description: Understand the model, boot the stack, and send your first authenticated request.
audience: integrator
status: IMPLEMENTED
scope: shipped-local
verifiedDate: "2026-10-21"
sourceOfTruth: services/proxy; services/auth; infra/compose/dev
---

::page-status{status="IMPLEMENTED" verified="2026-10-21"}
::

This section takes you from zero to a verified local request without hiding the parts that are still provisional.

## Recommended order

1. [Introduction](/docs/getting-started/introduction) — what the platform is and what runs today.
2. [Concepts](/docs/getting-started/concepts) — organizations, agents, PATs, sessions, memory, and context.
3. [Quickstart](/docs/getting-started/quickstart) — boot dependencies and send a mock completion.
4. [Local development](/docs/getting-started/local-development) — run services from source and know which ports they use.
5. [FAQ](/docs/getting-started/faq) — short answers to the questions people ask first.

::callout
---
{"type":"warning","title":"Read the claim boundary first"}
---

  “Implemented locally” does not mean hosted, HA, or production-ready. The platform has real auth, tenancy, and proxy code, but the production gates in [Production readiness](/docs/deployment/production-readiness) are still open.

::

## What you need

- Go 1.25+ and GNU Make for the Go services.
- Python 3.12+ with `uv` for the Python services.
- Docker Compose v2 for PostgreSQL, Redis, ClickHouse, and MinIO.
- No provider key for mock mode. Live mode requires an OpenAI, Anthropic, or self-hosted endpoint.

## What success looks like

A successful mock chat request proves that:

1. The proxy parsed your bearer PAT and called auth over gRPC.
2. `X-IBEX-Agent-ID` belongs to the token's organization and is active.
3. Rate limiting and request validation admitted the call.
4. The model resolved to a registered provider.
5. The response passed back through the proxy with correlation headers.

It does **not** prove that memory, context assembly, billing, or production recovery work. Those are separate surfaces with separate evidence.
