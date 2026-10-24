---
title: Proxy
description: The authenticated HTTP edge for chat completions, Responses, directives, sessions, and provider routing.
audience: integrator
status: IMPLEMENTED
scope: shipped-local
verifiedDate: "2026-10-21"
sourceOfTruth: services/proxy/README.md; services/proxy/internal/http/router_protected.go
---

The proxy is the public data-plane edge. It authenticates PATs, verifies agent identity, applies admission controls, optionally assembles context, and forwards to mock or live providers.

::page-status{status="IMPLEMENTED" verified="2026-10-21" note="Critical path is locally evidenced; hosted SLO remains open"}
::

## Start with the request path

- [Overview](/docs/proxy/overview) — endpoints, middleware order, headers, and failure modes.
- [Authentication](/docs/proxy/authentication) — bearer token, agent header, probes, and error semantics.
- [Request routing](/docs/proxy/request-routing) — model registry, provider selection, and fallbacks.
- [Idempotency and budgets](/docs/proxy/idempotency-and-budgets) — replay, admission holds, and usage accounting.
- [Sessions](/docs/proxy/sessions) — sticky session IDs and checkpoint behavior.
- [Directives](/docs/proxy/directives) — org directive resolution and system-prompt injection.
- [Rate limiting](/docs/proxy/rate-limiting) — Redis budgets and fail-closed behavior.
- [Provider adapters](/docs/proxy/provider-adapters) — mock, OpenAI, Anthropic, and self-hosted.
- [Provider routing and resilience](/docs/proxy/provider-routing-and-resilience) — model policy, capability manifests, breakers, and fallback.
- [Auth caching](/docs/proxy/auth-caching) — bloom + LRU and the revocation gate.
- [Configuration](/docs/proxy/configuration) — environment variables and startup validation.

## Implemented vs provisional

| Surface | Status | Boundary |
| --- | --- | --- |
| PAT and agent validation | IMPLEMENTED | Locally tested; auth gRPC must be trusted |
| Mock/live chat completion | IMPLEMENTED | Live provider calls depend on operator keys |
| Streaming | IMPLEMENTED | Provider-dependent; Responses streaming is rejected |
| Idempotency | IMPLEMENTED | Redis-backed for non-streaming chat |
| Sessions and directives | IMPLEMENTED | PostgreSQL/Redis required for durable behavior |
| Context assembly | PROVISIONAL | Optional; fails open to directive-only |
| Budget admission | PROVISIONAL | Ledger exists; reconciliation and hosted evidence open |

## Never infer

A successful mock response does not validate live provider behavior, context quality, billing correctness, or production throughput. A `501 PROVIDER_NOT_CONFIGURED` means the model is not in the active registry — not that forwarding is broken.
