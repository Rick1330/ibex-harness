# Runtime services

Deployable runtime components for IBEX Harness. This inventory describes the current repository, not a promise that every mounted route is production-certified. Use these status terms consistently:

- **Shipped:** implementation and local tests exist in the current source.
- **Mounted-but-provisional:** implementation is present, but hosted identity, deployment, rollout, or acceptance evidence is still open.
- **Deferred:** no current implementation should be assumed.

The public documentation site lives in [`web/`](../web/). The current phase snapshot is the [roadmap current state](https://ibexharness.com/roadmap/current-state).

## Current services

| Directory | Runtime role | Current status |
| --- | --- | --- |
| [`auth/`](auth/README.md) | Go AuthService: token validation, agent validation, PAT lifecycle, provider-credential metadata, session/TOTP primitives, health and metrics | **Shipped**, with production topology and key-management gates |
| [`proxy/`](proxy/README.md) | Go LLM proxy: auth, rate limits, provider forwarding, context injection, streaming, traces, and health/metrics | **Shipped**, with provider/deployment evidence tracked separately |
| [`api/`](api/README.md) | Python FastAPI management plane: tenant resources, tokens, providers, policies, billing/usage, legal holds, and operator reads/events | **Mounted and tested**; operator D1/D2 surfaces are provisional |
| [`memory/`](memory/README.md) | Python FastAPI memory write, semantic search, hot-cache, feedback, PII, deduplication, conflict, labels, and vector persistence | **Shipped locally**; hosted rollout and later retrieval capabilities remain gated |
| [`context/`](context/README.md) | Python context assembly library/gRPC service: budgets, retrieval, ranking, packing, and degradation behavior | **Shipped for trusted-boundary use**; current gRPC caller authentication limitation is explicit |
| [`embedder/`](embedder/README.md) | Python embedding service with deterministic CPU stub, TEI GPU backend, hosted backend, probes, and cache | **Shipped/experimental by profile**; backend readiness depends on external service configuration |
| [`mcp-memory/`](mcp-memory/README.md) | Python MCP memory resource server with AuthService boundary, memory tools, metrics, and optional audit sink | **Shipped/partial**; default audit is logging-only unless ClickHouse is configured |
| [`worker/`](worker/README.md) | Python Celery extraction, organization deletion, billing reconciliation/rollups, dead-letter handling, maintenance, and scheduled tasks | **Mixed:** several task families are shipped; explicit no-op tasks remain |
| [`console/`](console/README.md) | Canonical Next.js operator application and server-only DAL/BFF boundary | **Mounted-but-provisional:** D1/D2 metadata reads only; production identity and broader product surfaces are gated |
| [`dashboard/`](dashboard/README.md) | Legacy static connection/session/SSE shell | **Compatibility-only (4.P.0)**; do not expand as a second Track D product |

## Planned or intentionally absent services

No separate intelligence, search, tokenizer, or graph service is currently required. Intelligence extends `worker/`, `api/`, and `console/`; retrieval extends `memory/`, `context/`, and `mcp-memory/`. A new service requires measured evidence, a tenancy/security review, and an ADR.

## Ownership and evidence

Every service README must link its source entry points, tests, configuration, and known limitations. A route, schema, fixture, or README is not deployment evidence. Preserve explicit `org_id` filtering even when PostgreSQL RLS is enabled, and prefer 404 anti-enumeration behavior for cross-tenant resources.
