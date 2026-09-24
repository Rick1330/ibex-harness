# Operator Platform Architecture

## Purpose and status

This document defines the target architecture and evidence boundary for the operator product. The canonical authenticated application name is **`services/console`**. `web/` remains the public documentation site. `services/dashboard/` is only the temporary 4.P.0 compatibility shell and is not a second production product.

The repository baseline is commit `8f8e130` plus pre-existing review documents. Statements below distinguish four states: **implemented** means verified in the baseline; **mounted-but-provisional** means code is present but not production-ready; **specified-not-implemented** means a contract or design exists without a verified implementation; **deferred** means intentionally outside the current slice. A design contract is not deployment evidence.

## Product boundary

IBEX is an **auditable context-and-policy provenance debugger**. The operator UI consumes authenticated, versioned, tenant-scoped evidence; it is not the source of truth for traces, decisions, usage, or deletion. The visual/product mock is a preview and test baseline, never an evidence source.

## Surface status

| Surface | Status in baseline | Ownership and constraint |
|---|---|---|
| `web/` | Implemented public site | Public docs, roadmap, benchmark, and marketing content only. Do not place authenticated operator routes here. |
| `services/dashboard/` | Mounted-but-provisional | Static 4.P.0 connection/session/SSE compatibility shell. Retain while migration proceeds; do not expand it into Track D. |
| `services/console/` | Specified-not-implemented | Canonical Next.js operator application. Its package, workload, origin, and promotion evidence must be established before claiming implementation. |
| Overview/context/health/events contract | Mounted backend foundations, operator composition not fully verified | Ownership must remain server/API-side; the operator client must not infer missing evidence. |
| Explore, Trace Inspector, Sessions, Memories, Incidents, Directives, Drift, Billing, Analytics, Agents, Settings | Specified-not-implemented unless a separate implementation record proves otherwise | Enable one vertical slice at a time after data, security, contract, browser, and rollback gates pass. |
| Full production operator deployment and shell retirement | Deferred | Requires approved runtime ownership, staging browser promotion, rollback evidence, and parity decision. |

## Contract layers

| Layer | Required contract | Primary owner | Status boundary |
|---|---|---|---|
| Identity | session, tenant membership, permission, assurance, revocation | Auth service/API | Backend foundations exist; console integration is not claimed. |
| Operator context | principal, active organization, roles/permissions, step-up, feature/kill-switch state, allowed navigation | API/BFF | Specified; expose only fields verified by the server. |
| Overview | metrics with source, freshness, completeness, generated time, and optionality | API read model | Specified D1 contract; not a claim that all cards/charts exist. |
| Platform health | liveness/readiness and dependency-aware health facts | owning runtime/API | Existing service health is separate from an operator health composition. |
| Operator events | versioned SSE envelope, event ID, sequence, resume, deduplication, completeness | API/event plane | Shell parser is tested; production operator stream contract requires evidence. |
| Evidence | trace/span/event IDs, parent links, sequence, operation kind, status, provenance | evidence plane | Required data model; missing evidence is `unknown`, never fabricated. |
| Publication | event identity, aggregate sequence, schema version, digest, delivery state | Postgres outbox/relay | Target contract; replay and projection evidence required. |
| Governance | capture, redaction, retention, deletion, legal hold, audit | policy/audit stores | Target contract; TTL is not deletion SLA. |
| Query | typed filters, facets, cursors, freshness, completeness, URL state | API query contract | Specified; do not imply composed Explore APIs are live. |
| Control | intent, approval, before/after, idempotency, rollback | operator-action ledger | Deferred until the owning command pipeline is enabled. |
| Assurance | fixture, environment, commit, image, schema, result, artifact | CI/staging | Required evidence, not a current deployment claim. |

## Server-only DAL and BFF boundary

`services/console` must use a server-only DAL/BFF for privileged data. DAL modules must be marked `import 'server-only'`; resolve the authenticated session and organization on the server, authorize the request, call the owning API, validate the response, redact sensitive fields, and return minimal DTOs. Client components must never import server-only clients, bearer credentials, provider secrets, or raw tenant context.

Use Next.js proxy preprocessing only for lightweight routing/correlation concerns. Route Handlers are narrow same-origin BFF functions for session/bootstrap, CSRF-protected mutations, small composed reads, short-lived exports, or SSE forwarding when topology requires it. There must be no generic open proxy. Final authorization remains in the DAL and API.

## API contract ownership and validation

The owning backend service owns each contract; console owns presentation and client behavior, not truth. The API pipeline must produce a versioned **OpenAPI snapshot**, generate the TypeScript client from that snapshot, and run runtime validation at the BFF/DAL boundary. CI must fail on snapshot drift, generated-client drift, incompatible fixtures, or an unhandled response shape. SSE envelopes require a versioned schema validator and `Last-Event-ID` resume tests. Hand-maintained mock types are not a contract.

The initial D1 contract is limited to `context`, `overview`, `platform/health`, and `events` reads as approved by the API owner. Exact deployed paths, hostnames, and route availability remain an open decision unless verified by an implementation record.

## Security and response policy

The server enforces tenant and resource authorization on every request, stream, export, deletion, replay, and asynchronous job. Browser-supplied organization or resource IDs are never authorization inputs. Cross-tenant reads return a uniform not-found/empty result without existence leaks.

Authenticated personalized RSC, BFF, export, and SSE responses default to request-time **`no-store`**. Any exception requires an explicit tenant/key/scope design and tests for two roles and two tenants. Set `Cache-Control: no-store` on sensitive responses and prevent intermediary caching of streams and errors.

The approved topology must define secure cookies (`Secure` outside local development, `HttpOnly`, appropriate `SameSite`, narrow `Path`/`Domain`), CSRF validation for every cookie-authenticated mutation, exact credentialed CORS allowlists when origins differ, strict Origin/Referer checks, and SSE authorization/revocation/drain behavior. Security headers must include a reviewed CSP, `frame-ancestors`/`X-Frame-Options`, `Referrer-Policy`, `X-Content-Type-Options`, and a suitable Permissions-Policy. Values are topology decisions, not proof that they are currently deployed.

Prompts, tool arguments, outputs, links, HTML, Markdown, exports, and memory content are hostile untrusted data. Render inert/sanitized content and never expose provider secrets, bearer tokens, PAT plaintext, or raw sensitive payloads by default.

## Evidence and lifecycle

Content capture defaults to metadata-only. Redacted or privileged content requires a versioned policy, encrypted manifest, digest, retention class, deletion state, and verifiable receipt. ClickHouse TTL is storage hygiene, not application deletion SLA. Partial, sampled, redacted, late, expired, deleted, and simulated states are explicit on every read and SSE envelope.

Mandatory identifiers are not inferred from timestamps or content hashes: `trace_id` identifies distributed causality; `session_id` conversation grouping; `checkpoint_id` persisted turn snapshot; `span_id`/`parent_span_id` hierarchy; `event_id` one immutable event; `aggregate_seq` deterministic ordering.

## Deployment and runtime ownership

The deployment owner must explicitly choose one approved runtime for `services/console`: a versioned static artifact/workload with an approved BFF/API/SSE topology, or an approved transition runtime for the migration period. No hostname, ingress, Cloudflare project, Kubernetes workload, image, workflow, or production promotion is assumed from this document. The static compatibility shell may remain independently runnable until the canonical artifact has parity and rollback evidence.

Staging promotion must use the console artifact and authenticated browser evidence, not a public-docs smoke test. Promotion requires contract/OpenAPI and generated-client checks, four-role/two-tenant browser journeys, accessibility/visual/hostile-content/cache/SSE/performance gates, immutable artifact evidence, and a named rollback owner. Rollback must restore the prior known-good console artifact/digest and verify session, cache, SSE drain, and tenant boundaries. Retire `services/dashboard` only after an approved parity matrix, migration notice, rollback window, and removal of its workflow/runtime references; no retirement date is claimed here.

## Required trace prerequisites

The Trace Inspector is honest only when the evidence plane exposes stable join keys and payloads. Missing fields must be `unknown` or `not evaluated`, never zero or empty: trace/span/parent/aggregate identifiers; session/checkpoint/turn/request identifiers; assembly metrics; retrieval candidates and score schema; directive snapshot; sanitized tool audit; completeness and source watermark.

## Release evidence

A capability is promotable only when contract snapshots, golden fixtures, tenant-negative tests, redaction/deletion results, accessibility and performance reports, supply-chain evidence, deployment artifact digest, restore/rollback evidence, and staged browser results are linked. A route being designed or rendered from fixtures is not implementation evidence.

## References

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md), [DEPLOYMENT.md](DEPLOYMENT.md), [TESTING_STRATEGY.md](TESTING_STRATEGY.md), and [CONSOLE_DEEP_READINESS_PLAN.md](../../CONSOLE_DEEP_READINESS_PLAN.md) for the corresponding contract, runtime, test, and readiness rules.
