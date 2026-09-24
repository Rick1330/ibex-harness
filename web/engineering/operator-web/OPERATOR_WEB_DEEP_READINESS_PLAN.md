# IBEX Operator Web — Deep Readiness and Implementation Plan

**Status:** Research and architecture plan; no implementation changes made by this review.
**Repository baseline:** `ibex-harness` at `8f8e130`.
**Design baseline:** `/home/ubuntu/dash-board-mock/dash-board-mock`.
**Review scope:** repository architecture, mock transplant strategy, API contracts, security, evidence/data readiness, deployment, testing, and Next.js App Router quality.

## Documentation status taxonomy

This plan is a readiness proposal, not implementation evidence. Use **implemented** only for behavior verified in the baseline; **mounted-but-provisional** for present shell/backend foundations that still require production gates; **specified-not-implemented** for contracts, routes, packages, or workloads described here but not verified; and **deferred** for intentionally later work. The canonical name is `services/operator-web`; `web/` is public docs; `services/dashboard/` is a temporary compatibility shell. Do not infer hostnames, workflows, routes, deployment artifacts, or retirement from this plan.

## Executive conclusion

The repository and mock are not one dashboard today. They are three separate surfaces:

1. `web/` is the public documentation, roadmap, benchmark, and marketing site.
2. `services/dashboard/` is a small static 4.P.0 connection shell with provisional session, CSRF, API-origin, and SSE behavior.
3. `/home/ubuntu/dash-board-mock/dash-board-mock` is a broad Next.js operator product prototype with fixture-backed routes for Overview, Explore, Trace Inspector, Sessions, Memories, Incidents, Directives, Drift, Billing, Analytics, Agents, and Settings.

The correct strategy is to create **one canonical operator Next.js application inside the main repository**, preserve the mock as its product and visual baseline, and replace fixture behavior with real backend contracts one vertical slice at a time.

> **The mock should be transplanted before it is integrated. The design must be frozen before milestone implementation begins. The API, security, evidence, and operational truth must remain server-owned.**

The immediate goal is not to make every mock route live. The immediate goal is to establish a production-quality operator-web foundation, integrate the shell and 4.D.1 Overview, and create the contract and quality gates that prevent future design and security drift.

## What the research verified

The focused review covered eight independent areas: target architecture, mock design extraction, API boundaries, operator threat model, evidence/data contracts, deployment/runtime, testing/quality gates, and Next.js App Router implementation. The important verified findings are below.

### Repository architecture

The root workspace uses pnpm and Turbo. `pnpm-workspace.yaml` currently includes `web`, `packages/*`, and `services/dashboard`; the standalone mock is outside the workspace and has no Git metadata at the inspected path.

`web/` is a Next.js 16 application for the public site. Its package includes Fumadocs, roadmap content, benchmark pages, Vitest, and Playwright. Repository configuration references an `ibex-harness-docs` Cloudflare Pages project and `https://ibexharness.com`; treat those project/hostname references as documentation/configuration evidence only, not proof of a currently reachable deployment or final public hostname. The approved environment record must verify the public-docs origin before clients, tests, or rollback procedures use it.

`services/dashboard/` is a separate static SPA. Its README describes it as the 4.P.0 topology shell and explicitly says product UI is Track D. Its tested surface includes API-origin allowlisting, credentialed fetch behavior, login-body encoding, SSE parsing, event ID monotonicity, retry behavior, and reconnect backoff. It is not the full Track D product.

The mock is a separate Next.js 16.3.5/React 19.2.8 application with a historical/prototype inventory of 20 dashboard routes plus authentication routes, approximately 97 components, and 37 domain/lib files. That inventory is not evidence of mounted operator-web routes. It builds successfully in the reviewed prototype context, but its own lint command reports 19 errors and 6 warnings.

### Mock implementation quality

The mock has strong product structure. It has a shared shell, organization/environment context, time-range control, freshness and connection states, empty-state language, onboarding, responsive navigation, dark/light themes, and dedicated domain components.

Its domain model is much richer than the live operator surface. It contains typed concepts for provenance, candidate memory matrices, composite score explanations, session reconstruction, replay, incidents, evidence bundles, directives, drift, billing, audit, legal holds, tokens, providers, and webhooks.

Most domain adapters remain fixture-backed. Authentication uses browser-local simulated session state. Onboarding persists state in localStorage and includes `pat_plaintext` in the stored shape. Settings, analytics, billing, Explore, sessions, incidents, directives, and drift use fixtures, artificial delays, client-side authorization simulation, or locally generated values.

The visual design is not yet extraction-ready without cleanup. The lint run flags render-time `Math.random()` in a sidebar skeleton, render-time `Date.now()` in auth forms, multiple synchronous state writes inside effects, and other React Compiler/purity issues. The source also has placeholder `href="#"` pivots and raw anchors that should become typed Next.js routes.

Browser-level visual verification was not completed in this review because the attempted local dev server was not reachable. Therefore, the actual pixel-level behavior of mobile layout, focus rings, chart overflow, menu layering, and first paint remains an explicit verification task rather than a claimed result.

### API readiness

The FastAPI service has mounted/provisional foundations (not a complete operator product contract): `/v1` routers, Pydantic validation, cursor primitives, request IDs, normalized error handling, cookie sessions, CSRF middleware, credentialed CORS, operator session routes, operator SSE, platform health, billing, usage queries, organizations, agents, users, providers, tokens, rate limits, and privacy-related endpoints.

A maintained REST OpenAPI snapshot and generated TypeScript client were not verified in the inspected paths; treat both as specified-not-implemented until CI evidence exists. The mock domain types are hand-maintained and its adapters do not provide a shared runtime response parser, shared error taxonomy, or a production server-side data boundary.

No Next.js BFF Route Handlers were found in the mock. The mock supports a `NEXT_PUBLIC_IBEX_API_BASE` style client-side target and uses browser-side session simulation. That is appropriate for a prototype, not for a production privileged operator origin.

### Security readiness

The repository guidance requires explicit authentication, authorization, tenant filtering, fail-closed missing organization context, cross-tenant tests, no secret/raw-memory logging, approved cryptography, and safe treatment of memory content as untrusted input.

The backend has relevant controls, but gaps must be closed before production operator-web integration:

- The provisional HMAC refresh path is not equivalent to rotating AuthService refresh tokens and must not be reachable in staging or production.
- The reviewed operator SSE route verifies a signed cookie and organization binding, but its dedicated operator permission boundary must be explicitly confirmed and tested.
- Production cookie security is configuration-dependent; `Secure` defaults false in the inspected API settings and must be forced true outside local development.
- The mock stores synthetic sessions, CSRF state, and secret-like values in browser storage and must remain clearly non-production.
- Provider/webhook outbound validation needs centralized SSRF protection, redirect validation, DNS rebinding defense, port policy, and response/time limits across every call site.
- Authenticated API/RSC/export responses need explicit cache policy to prevent cross-user or cross-tenant leakage.
- Trace, memory, directive, incident, audit, provider, and export content require an explicit hostile-content and redaction policy.

### Evidence and data readiness

The repository has real write-side foundations. Postgres migrations define evidence runs, spans, events, session events, assembly metrics, score candidates, directive snapshots, tool audits, and an evidence outbox. ClickHouse migrations define traces, evidence spans, assembly metrics, and immutable usage facts.

However, the product read model is not ready for the full mock. No composed operator APIs for Explore, Trace detail/list, Sessions, Incidents, or evidence bundles were found. ClickHouse publication can be fail-open and bounded, so absence of a row cannot automatically mean absence of an event. The UI needs explicit freshness, completeness, sampling, retention, and source-watermark semantics.

Billing foundations exist, including rate cards, budgets, enforcement decisions, usage facts, rollups, and hard-cap middleware. Estimate-to-actual reconciliation is explicitly deferred, so the mock’s billing interface must keep advisory estimates separate from reconciled actual cost.

### Deployment and quality readiness

No operator-web deployment workflow or complete production promotion path was verified in the baseline. The existing static shell is provisional; any manual/preview process must be treated as transition-only until an artifact, runtime owner, staging browser gate, and rollback record exist. The Helm chart contains runtime workloads and security settings, but no operator-web workload, ingress/gateway, TLS contract, or complete browser promotion gate. Staging and production values include sentinel image digests that are not deployable until CI injects real artifacts.

The repository has useful unit and service tests, but the required operator-web assurance harness is not complete. The current web Playwright setup has two E2E specs and one Chromium project. There is no verified four-role/two-tenant fixture, visual baseline suite, axe gate, operator authenticated journey matrix, OpenAPI snapshot gate, or complete cross-tenant browser suite.

The branch protection inventory does not yet require the P.6/E.1 checks that the roadmap calls for. Those checks must exist and become required before any Track D completion claim.

## Canonical service decision

Create a new workspace service:

```text
services/operator-web/
├── src/
│   ├── app/
│   │   ├── (auth)/
│   │   ├── (operator)/
│   │   ├── api/
│   │   ├── loading.tsx
│   │   ├── error.tsx
│   │   ├── not-found.tsx
│   │   └── global-error.tsx
│   ├── components/
│   │   ├── ui/
│   │   ├── shell/
│   │   ├── data-state/
│   │   ├── evidence/
│   │   └── domains/
│   ├── lib/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── query-state/
│   │   ├── telemetry/
│   │   ├── security/
│   │   └── preview/
│   └── styles/
├── public/
├── tests/
├── next.config.ts
├── proxy.ts
├── package.json
└── tsconfig.json
```

Add `services/operator-web` to `pnpm-workspace.yaml`. Keep `web/` public and keep `services/dashboard/` as the temporary 4.P.0 compatibility shell during migration. Do not leave two production-intended dashboard implementations indefinitely; define a retirement gate for the static shell.

This decision avoids three common failures:

1. accidentally placing authenticated routes in the public docs site;
2. coupling operator release cadence to public documentation deployment;
3. losing the tested 4.P.0 origin/SSE behavior while replacing the shell.

The app should have a separate operator origin or a deliberately approved same-origin topology. The exact origin relationship must be decided in the 4.P.0 topology ADR before production cookies, CORS, CSRF, or SSE are finalized.

## Mock customization and transplant strategy

### Stage A: freeze the product baseline

Create a visual baseline release of the mock before moving code:

- route inventory;
- desktop and mobile screenshots;
- light and dark screenshots;
- shell expanded/collapsed screenshots;
- loading, empty, partial, stale, degraded, forbidden, and step-up screenshots;
- design-token inventory;
- component ownership map;
- fixture DTO inventory;
- current lint issue list;
- all placeholder routes and links.

The baseline is not a snapshot of every volatile chart pixel. Dynamic charts must use fixed data, frozen time, fixed locale, disabled motion, and a documented tolerance policy.

### Stage B: transplant without redesign

Copy the mock’s `src/app`, `src/components`, `src/lib` type/rationale files, `globals.css`, brand assets, and shadcn configuration into `services/operator-web` with the smallest possible visual delta.

Do not move fixture adapters into the production API layer. Move them into an explicit preview/test boundary. Every preview page must display a `Preview data` indicator and must not accept production session credentials or perform production mutations.

The first transplant PR should make the mock build in the monorepo. It should not connect real data.

### Stage C: clean deterministic behavior

Before live data:

- replace render-time `Math.random()` with fixed or seeded test-only values;
- move wall-clock reads behind an injected clock or client event;
- remove simulated random delays;
- replace localStorage session and secret persistence;
- replace placeholder anchors with typed route helpers or disabled actions;
- use `next/link` for internal navigation;
- split large client pages into server pages and interactive leaf components;
- fix the lint baseline without disabling rules;
- verify font loading and fallback behavior;
- add route-level loading/error/not-found boundaries.

### Stage D: preserve design through contracts

The mock’s visual states must be retained as a product contract. The API must provide enough metadata to support them:

```ts
type DataQuality = {
  completeness: "complete" | "partial" | "unavailable"
  freshness: "live" | "historical" | "stale" | "unknown"
  sampled: boolean
  retention: "within_policy" | "expired" | "unknown"
  generated_at: string
  source_versions: Record<string, string>
}
```

When the backend cannot supply a field, the UI should show `Unavailable`, `Partial data`, or an equivalent state from the mock language. It must not silently fill the gap with fixture data.

## Next.js application rules

### Server and client boundaries

Use Server Components for:

- route pages;
- authenticated layout and operator context;
- initial reads;
- server-side authorization-aware composition;
- minimal DTO construction.

Use Client Components only for:

- filter controls;
- charts requiring interaction;
- dialogs, tabs, menus, and sheets;
- replay controls;
- SSE subscription state;
- optimistic local drafts;
- browser-only accessibility or clipboard behaviors that have an explicit security policy.

Create a server-only DAL/API client and mark it with `import 'server-only'`. It should authorize the current session, obtain the server-side organization context, call the upstream API, validate the response, redact fields, and return minimal DTOs. This follows the current Next.js data-security guidance.[1]

### Proxy and Route Handlers

Use `proxy.ts` only for lightweight request preprocessing such as protected redirects, correlation headers, and route selection. Use a constant matcher that excludes static files, image optimization, public assets, API routes, and metadata paths. Do not put final authorization or data policy in Proxy; enforce that in the DAL and API routes.

Use Route Handlers only for narrow same-origin BFF functions such as:

- forwarding session/bootstrap operations;
- validating and forwarding CSRF-protected mutations;
- composing small operator reads;
- issuing short-lived export downloads;
- proxying SSE if the deployment topology requires it.

There must not be a generic open proxy route.

### Caching

Default authenticated personalized data to request-time/no-store behavior. Next.js 16’s caching model supports explicit cache components and `use cache`, but tenant-sensitive cache use is a security decision, not an automatic performance optimization.[3]

For every cached value, document:

- principal and organization in the cache key;
- permission/role version in the cache key or invalidation tag;
- filter/time-range dimensions;
- TTL and stale window;
- mutation invalidation;
- whether a CDN, server, or remote cache stores it.

Use Suspense for uncached runtime reads and provide the mock’s skeleton/loading states. Do not cache secrets, raw audit payloads, raw traces, one-time downloads, or mutation responses in shared caches.

### Error and loading boundaries

Every operator route must have an appropriate loading and error boundary. At minimum, create boundaries for:

- the shell;
- Overview;
- Explore;
- Trace detail;
- Sessions;
- Incidents;
- Settings;
- Billing;
- controlled actions.

Expected API outcomes should be typed into `forbidden`, `notFound`, `rateLimited`, `unavailable`, `partial`, `stale`, `degraded`, and `validation` states. Error boundaries should show a safe request ID and retry action without revealing upstream details.

## API and contract strategy

### Canonical contract flow

```text
FastAPI Pydantic schemas
  → reviewed OpenAPI snapshot
  → generated TypeScript types
  → runtime response validation
  → server-only domain clients
  → minimal page DTOs
  → mock-compatible view models
  → server/client UI components
```

Add a checked-in contract artifact, for example:

```text
contracts/management-v1.openapi.json
contracts/operator-events-v1.schema.json
contracts/operator-fixtures-v1/
```

Run an OpenAPI diff in CI. Breaking changes require an explicit version or compatibility migration.

### API client responsibilities

Create:

```text
src/lib/api/server-client.ts
src/lib/api/browser-client.ts
src/lib/api/envelope.ts
src/lib/api/errors.ts
src/lib/api/query.ts
src/lib/api/domains/context.ts
src/lib/api/domains/overview.ts
src/lib/api/domains/settings.ts
src/lib/api/domains/explore.ts
src/lib/api/domains/traces.ts
src/lib/api/domains/sessions.ts
src/lib/api/domains/incidents.ts
src/lib/api/domains/directives.ts
src/lib/api/domains/billing.ts
```

The shared boundary owns:

- upstream origin allowlisting;
- cookies and credentials;
- CSRF headers;
- request IDs and trace context;
- abort signals and deadlines;
- safe retry rules;
- response parsing;
- stable error classification;
- redaction before data crosses into client components.

Components must not call arbitrary `fetch` or know upstream URL configuration.

### Standard error envelope

Use the existing repository error conventions and ensure every operator response is classifiable:

```ts
type ApiError = {
  request_id: string
  status: number
  code: string
  message: string
  field_errors?: Record<string, string[]>
  retryable: boolean
  action?: "reauthenticate" | "step_up" | "retry" | "contact_admin"
}
```

The `message` must be safe for the user. Logs can contain a correlation ID and internal classification, but not secrets, raw memory, raw directives, or provider payloads.

### Query and URL state

Create a shared typed query codec for:

- organization/environment;
- time range;
- filters;
- sort;
- columns;
- cursor;
- selected resource;
- saved view identifier.

Rules:

- URL values are untrusted input;
- parse and bound all values;
- reset the cursor when filters or sort change;
- reject malformed or expired cursors safely;
- do not place secrets or raw content in URLs;
- preserve list context when opening detail;
- ensure browser back/forward reproduces the same state.

## Security and threat model

### Browser and XSS

Memories, prompts, directives, tool arguments, provider responses, incident evidence, and audit state are untrusted content. Render them as escaped text or through an approved sanitized format. Do not use `dangerouslySetInnerHTML` without a documented sanitizer policy. Validate links and disallow dangerous schemes.

Add a strict Content Security Policy compatible with the actual app. The inline theme bootstrap currently requires a nonce/hash-compatible approach or must be replaced. Add frame denial, HSTS at the HTTPS edge, `nosniff`, strict referrer policy, and restrictive Permissions-Policy.

Add hostile-content tests containing:

- HTML and SVG payloads;
- event-handler payloads;
- `javascript:` links;
- malformed Markdown;
- CSS injection attempts;
- tool arguments containing prompt-injection instructions;
- JSON with nested attacker-controlled strings.

### Session and authentication

Production should use the AuthService-owned RS256 session path with rotating refresh tokens, family revocation, reuse detection, and logout revocation. The provisional HMAC refresh path must be local-development-only or removed before shared environments.

Use:

- Secure cookies outside local development;
- HttpOnly access/refresh cookies;
- readable CSRF cookie only where required by the double-submit pattern;
- exact SameSite and Domain decisions in the topology ADR;
- strict Origin/Referer checks for cookie mutations;
- short-lived access tokens;
- refresh reuse detection;
- server-side revocation propagation;
- step-up freshness bound to action and organization.

Never store sessions, CSRF secrets, PAT plaintext, provider keys, webhook secrets, or TOTP material in localStorage/sessionStorage.

### CSRF and CORS

If UI and API are cross-origin:

- use an exact allowlist, never wildcard credentialed CORS;
- allow only required methods and headers;
- expose only required response headers;
- validate Origin/Referer on state-changing requests;
- use the repository CSRF token pattern;
- test preflight, credentialed success, foreign-origin rejection, missing token, mismatched token, and expired session.

If UI and API are same-origin through a BFF, retain CSRF protection for all cookie-authenticated mutations.

### Tenant isolation and IDOR

The active organization is selected only after server membership validation. A browser-supplied `org_id`, `trace_id`, `session_id`, `incident_id`, or `action_id` is never an authorization input.

Every read and mutation must enforce:

- authenticated principal;
- organization membership;
- permission bitmap;
- role requirement where applicable;
- resource ownership or tenant scope;
- step-up for privileged action;
- uniform cross-tenant `404` or empty-search behavior.

Add Org A/Org B tests for every new endpoint, stream, export, replay, deletion, and settings resource.

### Cache and data leakage

Authenticated RSC payloads, API responses, exports, and SSE must not be publicly or cross-user cached. Add browser-level cache tests that authenticate as two roles and two organizations, perform the same navigation, and assert that no response or rendered state crosses the boundary.

### SSRF and outbound requests

Provider validation and webhooks are SSRF surfaces. Centralize outbound requests and enforce:

- HTTPS or approved scheme only;
- approved ports;
- no loopback, private, link-local, multicast, reserved, metadata, or Unix-socket targets;
- DNS resolution and address pinning;
- revalidation on redirects or redirects disabled;
- response size limits;
- strict connect/read/total timeouts;
- no credential forwarding to redirected hosts;
- audit classification without logging keys or bodies.

Add DNS rebinding, IPv4-mapped IPv6, alternative numeric forms, redirect-to-private, metadata IP, and oversized-response tests.

### Secrets and exports

Provider credentials, PAT plaintext, webhook secrets, TOTP secrets, raw prompt/memory data, and evidence bundles need separate classification and lifecycle rules.

Default to:

- encrypted server-side storage;
- one-time plaintext response;
- no browser persistence;
- no logs or traces containing plaintext;
- no general list endpoint returning secret material;
- short-lived signed downloads for authorized exports;
- server-side export job with audit and step-up;
- no-store on download and error responses;
- deletion and legal-hold coordination.

### Controlled actions

Delete, replay, raw-read, export, secret-use, directive promotion, routing changes, and incident state changes need one centralized command pipeline:

```text
authenticate
→ resolve organization
→ authorize permission/role
→ verify feature flag and kill switch
→ verify fresh step-up
→ validate request and resource ownership
→ validate idempotency key
→ validate preview token or approval state
→ require second actor if policy requires
→ perform transaction/outbox write
→ append action ledger
→ publish result and audit event
```

A UI button is not a control. The backend must enforce the entire sequence.

## Evidence and read-model strategy

### D1 read model

Start with a minimal real contract:

```text
GET /v1/operator/context
GET /v1/operator/overview
GET /v1/operator/platform/health
GET /v1/operator/events
```

`OperatorContext` should include the authenticated principal, active organization, roles/permissions, step-up status, feature/kill-switch state, and allowed navigation capabilities.

`OperatorOverview` should include metrics with source, completeness, freshness, generated time, and optionality. It should not expose a chart field that the backend cannot explain.

### D2 provenance model

Before connecting the full Trace Inspector, define the identity relationship among:

- `org_id`;
- `request_id`;
- `trace_id`;
- `root_span_id` and `span_id`;
- `run_id`;
- `session_id`;
- `checkpoint_id`;
- `turn_sequence`;
- `memory_id`;
- `directive_version_id`;
- usage fact IDs.

Define cardinality and retry behavior. Decide whether a request can have multiple traces or evidence runs, how retries are represented, and how expired content appears.

Use Postgres evidence as the durable authoritative index and ClickHouse as a query projection where appropriate. Every response should expose source watermarks or an equivalent completeness indicator when projections can lag or drop rows.

### D3 sessions and replay

Do not call the mock session page “replay” until the repository has:

- immutable checkpoint identity;
- governed raw/conversation storage;
- retention and legal-hold semantics;
- deterministic replay contract;
- policy/directive/tokenizer/model version capture;
- safe redaction;
- export/delete receipts;
- step-up and audit.

### D4 incidents and bundles

Implement an incident state machine and bundle contract before enabling mock incident writes. A bundle needs a stable evidence selection, redaction state, digest/signature, retention policy, actor, request ID, and immutable transition history.

### D5 controlled actions

Keep the mock promotion console disabled or read-only until directive versioning, routing provenance, preview, approval, step-up, idempotency, action ledger, staged rollout, and rollback are real.

Keep drift behind the Phase 4.5 fingerprint producer contract.

### D6 cost governance

The Billing UI can first expose advisory estimated spend. It must label:

- estimate versus actual;
- rate-card version;
- enforcement mode;
- source watermark;
- reconciliation status;
- completeness;
- late/duplicate fact count.

Hard caps must use durable enforcement decisions and pass concurrent over-admission, retry, reconciliation, rollback-to-alert-only, and no-double-charge tests.

## Deployment and environment strategy

### Environment matrix

Create one canonical environment-origin matrix and use it to generate or validate configuration:

| Environment | Operator UI | API | Cookie policy | Data mode | Release policy |
|---|---|---|---|---|---|
| Local | loopback | loopback | Secure optional only locally | deterministic preview/test | developer only |
| Preview | protected preview origin | staging or isolated API | Secure required | seeded test data | branch/PR |
| Staging | approved operator staging origin | staging API | Secure, exact origin | real topology and seeded tenants | promotion gate |
| Production | approved operator origin | production API | Secure, exact origin | real tenant data | protected promotion |

The topology ADR must decide whether UI and API are same-origin or cross-site, then define TLS termination, cookie Domain/Path/SameSite, CORS, CSRF trusted origins, CSP `connect-src`, SSE proxy timeout, and rollback.

### Headers and caching

Operator responses must include an approved security header set. At minimum:

- Content-Security-Policy;
- Strict-Transport-Security in HTTPS environments;
- frame-ancestors or X-Frame-Options;
- X-Content-Type-Options;
- Referrer-Policy;
- Permissions-Policy;
- explicit Cache-Control for HTML, RSC, API, downloads, and SSE.

### Container and cluster

If operator-web is deployed as a container, add:

- immutable image digest;
- SBOM and provenance;
- signature and admission verification;
- non-root/read-only filesystem;
- resource requests and limits;
- startup/readiness/liveness probes;
- graceful SSE drain/preStop behavior;
- NetworkPolicy;
- PDB where appropriate;
- secret references, not inline secret values;
- staged rollout and rollback.

If the UI remains static on Pages, still require immutable assets, exact API configuration, CSP, cache rules, authenticated browser smoke tests, and a rollbackable Pages deployment. The API/runtime topology cannot remain README-only.

### Observability

Add operator-web and API telemetry for:

- page and API latency p50/p95/p99;
- request counts and status classes;
- authentication and CSRF failures;
- organization/permission denials;
- SSE active connections, reconnects, resume gaps, and lag;
- query freshness/completeness;
- evidence publication lag;
- export/replay/action outcomes;
- frontend errors with safe request IDs;
- deployed UI/API/image digests.

Logs must be structured with request ID, trace ID, and organization ID where available, while centrally redacting secrets and sensitive content.

## Testing and quality gate

### Required local and CI commands

The canonical operator package should expose:

```text
pnpm --filter operator-web lint
pnpm --filter operator-web typecheck
pnpm --filter operator-web test
pnpm --filter operator-web test:contract
pnpm --filter operator-web test:a11y
pnpm --filter operator-web test:visual
pnpm --filter operator-web test:e2e:smoke
pnpm --filter operator-web build
```

The CI environment must install dependencies with a frozen lockfile, install pinned browsers, and publish test artifacts.

### Browser matrix

At minimum test:

- Chromium desktop;
- Chromium mobile viewport;
- one additional supported browser if the production support policy requires it;
- light and dark themes;
- reduced motion;
- keyboard-only operation;
- four roles across two organizations.

### Required browser journeys

D1:

- login;
- refresh;
- logout;
- session expiry;
- organization switching;
- unauthorized organization deep link;
- Overview live/partial/stale/degraded/empty states;
- SSE reconnect and drain;
- mobile sidebar and keyboard navigation.

D2:

- Explore filters and URL round trip;
- stable cursor pagination;
- Trace detail pivots;
- cross-tenant trace denial;
- hostile content safe rendering;
- completeness and retention labels;
- metadata-only degraded mode.

D3–D6 as their contracts land:

- session/memory evidence;
- governed export/delete;
- incident ownership and bundle evidence;
- directive preview/approval/rollback;
- hard-cap denial;
- reconciliation state;
- no-double-charge retry;
- drift gating.

### Visual and accessibility

Use baseline screenshots for stable shell and state surfaces. Freeze clock, locale, timezone, fonts, data, and motion for snapshots. Review intentional diffs rather than accepting automatic updates.

Run axe or equivalent checks on critical routes. Also verify:

- heading hierarchy;
- landmarks;
- visible focus;
- keyboard controls;
- live status announcements;
- chart summaries;
- non-color status communication;
- dialog focus trapping;
- mobile sheet behavior;
- zoom and long-content behavior.

### Contract and tenant testing

Require OpenAPI snapshot diff, generated-client freshness, SSE schema validation, runtime DTO parsing, and a four-role/two-tenant test manifest. Real Postgres RLS, Redis Lua, pgvector, and revocation paths must be exercised where the roadmap requires them; doubles are not evidence for these controls.

### Performance and resilience

Track E.2 should measure:

- initial shell and Overview data time;
- Explore query p50/p95/p99;
- Trace detail open latency;
- SSE reconnect/resume and slow-client behavior;
- frontend JavaScript and hydration budget;
- API dependency errors;
- queue lag and evidence publication lag;
- memory and CPU;
- cost and concurrency limits;
- rollback time and restore RPO/RTO.

## Phased implementation plan

### Phase 0 — decisions and no-code readiness

Deliver:

- topology ADR;
- environment-origin matrix;
- canonical operator service decision;
- visual baseline inventory;
- data classification matrix;
- API ownership matrix;
- evidence identity/cardinality decision;
- release/rollback owner;
- initial threat model;
- explicit list of D1 routes and deferred routes.

Exit condition: no unresolved decision would change the application boundary, cookie topology, data classification, or first production slice.

### Phase 1 — transplant and build quality

Deliver:

- `services/operator-web` package;
- mock route/component transplant;
- deterministic clock and fixture boundaries;
- lint cleanup;
- route helpers replacing placeholders;
- loading/error/not-found boundaries;
- screenshot and accessibility harness;
- preview/test/production mode separation.

Exit condition: build, lint, typecheck, visual baseline, and deterministic test suite pass without real credentials or production data.

### Phase 2 — real shell and authentication

Deliver:

- server-only session client;
- real login/refresh/logout/me;
- CSRF and exact origin behavior;
- organization context;
- permission/feature/kill-switch context;
- platform health and SSE state;
- secure headers and cache policy.

Exit condition: four roles/two tenants, session expiry/revocation, CSRF, origin, SSE reconnect/drain, and shell visual/accessibility journeys pass.

### Phase 3 — D1 Overview

Deliver:

- context and Overview contracts;
- real Overview cards/charts using mock composition;
- freshness/completeness model;
- URL time-range state;
- onboarding read/write contract;
- route-level feature flag and rollback.

Exit condition: D1 checklist evidence is attached and P.0/P.1 minimum contracts are closed.

### Phase 4 — settings and governance

Deliver:

- real organization/user/agent/token/provider/settings reads;
- permissions and step-up;
- legal holds and deletion receipts;
- action ledger outcomes;
- one-time secret behavior;
- audit redaction/export contract.

Exit condition: mutation, tenant, redaction, export, and permission tests pass.

### Phase 5 — P.2/P.4 read contracts

Deliver:

- OpenAPI snapshots and generated client;
- canonical trace identity joins;
- Overview/Explore read models;
- completeness/freshness/retention/watermark fields;
- cursor/query grammar;
- billing reconciliation contract.

Exit condition: D2 can begin without presenting unjoinable or unverifiable evidence.

### Phase 6 — D2 and later slices

Deliver in order:

1. Explore and metadata-first Trace Inspector;
2. sessions, memory, context, and safe replay;
3. failures, incidents, and evidence bundles;
4. directives, routing, experiments, and controlled actions;
5. usage, cost governance, and capacity.

Exit condition: each slice has backend contract, fixture/fixture parity, visual baseline, accessibility evidence, tenant-negative tests, telemetry, and rollback.

### Phase 7 — production promotion and shell retirement

Deliver:

- staging deployment;
- authenticated browser promotion suite;
- signed artifacts and admission checks;
- resilience/recovery evidence;
- staged rollout and rollback;
- support/runbooks;
- static shell coexistence and cutover;
- retirement of `services/dashboard` after parity.

## PR-sized execution plan

### PR 1 — topology and ownership decision

No UI changes. Add the topology ADR, origin matrix, ownership matrix, and shell retirement criteria.

### PR 2 — operator-web seed

Copy the mock into the new workspace package. Preserve visual output. Do not connect real APIs.

### PR 3 — deterministic and navigation cleanup

Remove render randomness, wall-clock nondeterminism, placeholder links, raw internal anchors, and fixture secrets. Fix lint without weakening rules.

### PR 4 — visual and accessibility harness

Add visual baselines, deterministic browser fixtures, axe, keyboard journeys, reduced-motion coverage, and artifact upload.

### PR 5 — server-only API boundary

Add the server DAL/client, runtime parsing, error envelope, request IDs, timeouts, and preview/test transport separation.

### PR 6 — session and shell integration

Connect session, CSRF, organization context, health, SSE, route flags, security headers, and cache policy.

### PR 7 — D1 Overview

Connect only Overview and onboarding reads. Preserve mock layout and states. Add D1 evidence.

### PR 8 — settings and governance

Connect existing management/privacy/legal-hold/token/provider APIs with real permission and audit behavior.

### PR 9 — P.2/P.4 contract closure

Add OpenAPI snapshots, generated client, trace joins, query grammar, completeness/watermarks, and billing reconciliation contract.

### PR 10 onward — evidence-gated Track D

Implement D2–D6 in the roadmap order. Do not enable a route because the front end is complete; enable it only when its backend, security, data, quality, and rollback gates are complete.

## Decision register

The following decisions are recommended now:

| Decision | Recommendation | Why |
|---|---|---|
| Canonical operator app | New `services/operator-web` | Separates public docs and authenticated product concerns. |
| Mock role | Visual/product baseline and preview/test source | Preserves quality without treating fixtures as truth. |
| Production data path | Server-only DAL/BFF with typed DTOs | Centralizes authorization, redaction, caching, and errors. |
| Auth | AuthService RS256 rotation and revocation | Removes provisional HMAC risk from shared environments. |
| Cache default | Request-time/no-store for personalized data | Prevents cross-tenant leakage while contracts mature. |
| D1 scope | Shell, context, Overview, health, freshness, navigation | Highest-value slice with existing backend foundations. |
| D2 scope | Metadata-first until P.2 joins close | Prevents false provenance claims. |
| Drift | Disabled/experimental until Phase 4.5 producer contract | Roadmap dependency is explicit. |
| Billing | Estimates visibly separate from actuals | Reconciliation is not complete. |
| Static shell | Compatibility layer only | Avoids losing tested 4.P.0 behavior during migration. |

## Open questions that must be answered before Phase 1 implementation

1. What are the final production hostnames for public web, operator UI, and API?
2. Is UI/API same-origin, same-site cross-subdomain, or intentionally cross-site?
3. Who owns the AuthService session lifecycle and when can the provisional HMAC path be removed?
4. Which backend service owns each operator domain contract?
5. What is the canonical identity/cardinality relationship between request, trace, span, run, session, checkpoint, memory, directive, and usage fact?
6. What is the raw/conversation storage and retention policy?
7. Which operator actions are enabled in D1, and which remain read-only?
8. What is the first real staging environment for authenticated browser tests?
9. What accessibility standard and supported browser matrix are required?
10. What are the page/query/SSE performance budgets and SLO thresholds?
11. What is the rollout and rollback owner for UI/API compatibility?
12. When can `services/dashboard` be retired?

These are not blockers to research; they are blockers to making irreversible architecture or security assumptions.

## Readiness gate before writing production UI code

Do not start live integration until these are approved:

- canonical operator service location;
- topology ADR and environment matrix;
- session/cookie/CSRF/CORS/SSE rules;
- API ownership and OpenAPI versioning policy;
- data classification and redaction policy;
- evidence identity/cardinality decision;
- D1 route list and deferred route list;
- production/preview/test fixture boundary;
- visual baseline and acceptance process;
- CI quality checks and artifact ownership;
- rollback and static-shell coexistence plan.

Once these are approved, Phase 1 can proceed safely. Until then, adding more dashboard screens would create precisely the design and implementation drift the strategy is intended to prevent.

## References

[1]: https://nextjs.org/docs/app/guides/data-security "Next.js Data Security Guide"
[3]: https://nextjs.org/docs/app/getting-started/caching "Next.js Caching Guide"
