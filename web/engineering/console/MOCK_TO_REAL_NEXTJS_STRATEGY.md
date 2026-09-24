# Mock Dashboard → Real IBEX Operator Dashboard

## In-depth migration, design-preservation, and quality strategy

**Purpose:** Use the submitted mock dashboard as the exact product and visual baseline while replacing its fixture-backed behavior with the real IBEX repository contracts, APIs, evidence, tenancy, and deployment model.

**Core principle:**

> **Do not redesign the dashboard while implementing the milestones. Freeze the mock as the product baseline, then implement real contracts underneath it.**

The recurring quality problem is not that the milestones are wrong. It is that milestone work starts from backend requirements and recreates the UI from prose. That causes design drift, inconsistent states, and a loss of the visual quality already present in the mock.

The solution is to separate the work into two deliberately different tracks:

1. **Product surface track:** the mock owns layout, hierarchy, interaction language, visual tokens, component behavior, responsive rules, and state presentation.
2. **Reality track:** the main repository owns authentication, tenancy, API contracts, evidence, persistence, governance, telemetry, and deployment.

Every vertical slice is accepted only when both tracks meet the same contract.

---

## 1. Target architecture

### 1.1 Create a dedicated operator Next.js application

The main repository currently has two different front-end concerns:

- `web/`: the public docs, roadmap, benchmark, and marketing site;
- `services/dashboard/`: a static 4.P.0 connection shell.

The mock is a full Next.js operator product and should not be forced into the public docs app or permanently constrained by the static shell. The recommended target is:

```text
services/console/
├── src/app/
├── src/components/
├── src/lib/
├── public/
├── tests/
├── package.json
├── next.config.ts
└── tsconfig.json
```

Add `services/console` to `pnpm-workspace.yaml`.

This keeps the boundaries clear:

| Application | Responsibility | Origin |
|---|---|---|
| `web` | Public documentation, roadmap, benchmarks, marketing | Public docs origin |
| `services/console` | Authenticated operator product | Operator origin |
| `services/api` | Management, operator, tenant-scoped APIs | API origin or same-origin BFF |
| `services/dashboard` | Temporary 4.P.0 compatibility shell | Retire after parity |

Do not merge the operator product into `web` merely because both use Next.js. Their auth, caching, security posture, release cadence, and content boundaries are different.

### 1.2 Preserve the mock’s application shape

The mock already uses a good Next.js foundation: App Router, React Server Components, client components for interactions, typed domain libraries, shadcn-style primitives, responsive layout, and theme support.

The first implementation should be a **controlled transplant**, not a rewrite. Copy the mock into `services/console`, make it build in the monorepo, and only then replace data adapters.

Preserve initially:

- route names;
- component boundaries;
- CSS variables and color tokens;
- typography, spacing, and density;
- responsive breakpoints;
- empty/error/partial/stale/degraded state language;
- interaction patterns;
- loading and transition behavior;
- accessibility attributes.

### 1.3 Establish a visual baseline before real API wiring

Before any production integration, create a baseline release of the mock:

- light and dark screenshots for every route;
- desktop and mobile screenshots;
- loading, empty, error, partial, stale, degraded, forbidden, and step-up states;
- route inventory and navigation map;
- design-token export;
- fixture DTO inventory per route.

These screenshots become visual regression fixtures. A milestone cannot change the visual system silently. Any intentional visual change updates the baseline and records why.

---

## 2. Treat the mock as a design system, not a pile of pages

### 2.1 Freeze design primitives

Extract the mock’s visual rules into explicit design tokens and shared primitives:

```text
services/console/src/styles/tokens.css
services/console/src/components/ui/
services/console/src/components/shell/
services/console/src/components/data-state/
services/console/src/components/metrics/
services/console/src/components/evidence/
```

The token set covers semantic colors, chart colors, typography, mono versus sans usage, radius, spacing, control heights, sidebar widths, density, motion, and focus rings.

Individual milestone work must not introduce arbitrary colors, spacing, or typography. New visual values require a token update and visual review.

### 2.2 Define component ownership

| Layer | Examples | Rule |
|---|---|---|
| Primitive UI | Button, Input, Badge, Dialog, Tabs, Tooltip | Generic; no domain policy. |
| Shell | Sidebar, org switcher, header, breadcrumbs, time range, health state | Shared across every operator route. |
| Data state | Loading, empty, partial, stale, degraded, forbidden, error | Consistent across all pages. |
| Evidence | Provenance link, completeness marker, redacted payload | Must not imply stronger evidence than the API provides. |
| Domain | Trace matrix, incident timeline, promotion console, budget card | Owns domain layout; consumes DTOs. |
| Page | Explore, incidents, settings, overview | Composes; does not implement policy. |

A page must not create one-off versions of the shell, filters, state badges, or authorization gates.

### 2.3 Give every page a design contract

Each route gets a short contract containing:

- operator question and success outcome;
- route and deep-link grammar;
- page anatomy;
- primary and secondary actions;
- responsive behavior;
- empty/error/partial/stale/degraded states;
- permission and step-up states;
- telemetry events;
- screenshot baseline IDs;
- DTOs consumed;
- feature flag and rollback behavior.

This is the visual equivalent of an API contract and prevents quality loss when implementation changes hands.

---

## 3. Real Next.js data architecture

### 3.1 Use Server Components by default

Use:

- **Server Components** for route pages, layouts, initial reads, and authorization-aware composition.
- **Client Components** only for filters, menus, charts with interaction, dialogs, tabs, replay controls, SSE subscriptions, optimistic UI, and local drafts.
- **Route handlers/BFF only where needed** for same-origin proxying, cookie forwarding, CSRF protection, and small API aggregations.

Do not convert entire pages to client components merely because one chart or dropdown is interactive.

### 3.2 Create one typed API boundary

Add a single API client layer, rather than allowing components to call `fetch` directly:

```text
src/lib/api/
├── server-client.ts       # authenticated server-side reads/writes
├── browser-client.ts      # browser-safe same-origin calls
├── errors.ts              # stable error classification
├── envelope.ts            # API envelope parsing
├── query.ts               # URL/query grammar
└── domains/
    ├── operator-context.ts
    ├── overview.ts
    ├── explore.ts
    ├── traces.ts
    ├── sessions.ts
    ├── incidents.ts
    ├── directives.ts
    ├── billing.ts
    └── settings.ts
```

The client layer owns:

- base-origin allowlisting;
- request IDs;
- cookies and credentials;
- CSRF headers;
- timeout and abort behavior;
- stable error classification;
- response validation;
- retry policy only for safe reads;
- telemetry around failures.

Components receive typed results, not raw `Response` objects.

### 3.3 Generate or derive contracts from the API

The FastAPI management service should expose versioned OpenAPI. Generate TypeScript types from that contract and validate runtime responses with Zod at the boundary.

The flow should be:

```text
FastAPI schemas
  → OpenAPI snapshot
  → generated TypeScript types
  → Zod response validators
  → domain API client
  → page/view-model adapters
  → mock-compatible components
```

The mock’s existing types become the target product shape, but they must be reconciled with the authoritative server DTOs. When a field is unavailable, the UI must show an explicit unavailable/degraded state rather than fabricate it.

### 3.4 Model every response with completeness

Every read model that powers the dashboard should support a shape like:

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

This enables the mock’s strong honesty language to be backed by real data instead of being purely visual.

### 3.5 Authentication and tenancy rules

The browser must not hold long-lived secrets or use fixture auth in production:

- use the repository’s HTTP-only operator session cookies;
- use CSRF protection for mutations;
- keep PAT plaintext display one-time only;
- forward tenant context from authenticated claims, not a browser-selected arbitrary `org_id`;
- use the selected organization only after the server confirms membership;
- return `404` or empty search results for unauthorized cross-tenant resource lookups according to the API contract;
- require step-up for privileged settings, replay, export, deletion, and controlled actions;
- keep feature flags and kill switches server-authoritative.

The mock’s auth provider becomes a test double only. It must not survive into production bundles as a selectable data path.

---

## 4. Deterministic quality: eliminate random and unreviewable behavior

### 4.1 Production code must be deterministic

The mock currently has fixture values and a render-time `Math.random()` skeleton width. Before real integration:

- remove `Math.random()` from render paths;
- inject a deterministic skeleton width or use fixed CSS variants;
- inject a clock for relative timestamps;
- avoid `new Date()` in render-time fixture creation;
- give every fixture stable IDs;
- use seeded fixture factories in tests only;
- do not use random delays to simulate network behavior;
- do not use localStorage as a substitute for server truth.

Add an ESLint rule or code-review rule that rejects `Math.random()` in `src/components` and rejects unbounded `Date.now()`/`new Date()` in deterministic view logic.

### 4.2 Separate fixture, preview, and production modes

Use three explicit modes:

```text
production  → real API only
preview     → contract fixtures, visibly labeled, never mixed with production auth
test        → deterministic fixtures and network interception
```

Fixture data belongs under:

```text
src/test/fixtures/
src/test/factories/
src/test/msw/
```

Do not keep fixture APIs under `src/lib/*/api.ts` with the same names as production clients. That makes accidental production wiring likely.

### 4.3 Keep design previews useful

A preview route can remain available for design review, but it must have:

- a visible `Preview data` banner;
- no production credentials;
- deterministic data;
- direct links to every state variant;
- no ability to mutate production;
- a separate build or environment flag.

This allows designers and reviewers to continue using the mock-quality surface while engineering connects one real domain at a time.

---

## 5. Migration phases

### Phase 0 — Product and visual lock

**Goal:** Make the mock the authoritative baseline.

Deliverables:

- copy the mock into a dedicated branch or `services/console` seed;
- record the mock source commit/hash;
- fix lint issues that affect correctness or determinism;
- capture route/state screenshots;
- inventory all fixture DTOs and actions;
- publish the design contract for shell, overview, Explore, Trace Inspector, sessions, incidents, directives, billing, and settings;
- decide the operator origin and deployment topology.

Exit gate:

- the app builds;
- the route inventory is complete;
- screenshots are approved;
- no designer-level visual changes are mixed into API work.

### Phase 1 — Monorepo transplant

**Goal:** Run the mock as a first-class repository application without changing its design.

Deliverables:

- create `services/console`;
- add it to the pnpm workspace;
- align versions with the repository’s Next 16/React 19 stack;
- use repository lint, TypeScript, formatting, and CI conventions;
- preserve path aliases and shadcn configuration;
- add a standalone dev/build/start command;
- add a separate operator-origin deployment target;
- keep `services/dashboard` as a compatibility shell during migration.

Exit gate:

- `pnpm --filter console build` passes;
- the mock screenshots have no unintended visual diff;
- the public `web` app remains unaffected;
- the operator app is not accidentally indexed as public docs.

### Phase 2 — Real shell and authentication

**Maps to:** 4.P.0, 4.P.1, 4.D.1.

Replace only the mock shell plumbing first:

- mock auth provider → real operator session cookies;
- mock org switcher → authenticated organization list and selection;
- mock shell health fixture → `/ready`, platform health, and SSE state;
- mock relative time → server-provided `last_successful_sync` and injected clock;
- fixture route availability → server-authoritative feature/kill-switch response;
- mock login outcomes → real error taxonomy and cooldown/step-up behavior.

Do not add deep domain pages to production routing until this shell is real.

Exit gate:

- login, refresh, logout, CSRF, and session expiry work;
- four roles and two tenants are tested;
- org switching cannot escape tenant authorization;
- SSE reconnect/drain state matches the visual contract;
- the entire shell has light/dark and mobile screenshot coverage.

### Phase 3 — D1 Overview vertical slice

**Maps to:** 4.D.1.

Implement the real Overview behind the existing mock layout:

- real Overview DTO;
- agent/resource summary;
- health and freshness cards;
- request/token/latency panels;
- partial ClickHouse bucket behavior;
- onboarding checklist backed by server facts or a clearly bounded settings contract;
- global time-range URL state;
- loading, empty, partial, stale, degraded, forbidden, and error states;
- Explore, Incidents, Sessions, and Settings navigation entries.

No visual redesign occurs in this phase. The page is complete only when the real data appears in the same visual composition and state language as the mock.

Exit gate:

- D1 design screenshots pass;
- real API contract snapshots pass;
- four-role/two-tenant Playwright journeys pass;
- axe and keyboard checks pass;
- performance budget passes;
- route-level rollback disables the surface without affecting the data plane.

### Phase 4 — Settings and governance foundations

**Maps to:** 4.P.1, 4.P.3, parts of 4.D.5 and 4.D.6.

Connect the mock settings surfaces to the existing repository APIs:

- organizations and users;
- agents;
- PAT tokens;
- providers and validation;
- rate limits and model policies;
- capture policies;
- legal holds;
- privacy/deletion workflows;
- operator action ledger;
- platform health.

This is the safest second integration because the repository already has many corresponding APIs and tests. It also validates the permissions, step-up, tenant isolation, and mutation patterns needed by later pages.

Exit gate:

- every mutation has a stable request ID and audit outcome;
- permission-denied, step-up-required, feature-off, and tier-limited states match the mock;
- secrets are displayed once and never re-fetched;
- real cross-tenant negative tests pass;
- deletion and legal-hold receipts are authoritative.

### Phase 5 — Explore and metadata-first Trace Inspector

**Maps to:** 4.P.2, 4.P.4, 4.D.2.

Use the mock Trace Inspector as the acceptance target, but deliver it in layers:

1. Explore query bar, filters, facets, and URL grammar.
2. Metadata-only trace list and summary.
3. Joinable `request_id`, `trace_id`, `span_id`, `session_id`, and checkpoint IDs.
4. Completeness, sampling, freshness, and retention badges.
5. Candidate matrix with explicit Included, Budget-excluded, Filtered, and Failed groups.
6. Composite score explanation using a versioned payload.
7. Timeline, tool metadata, routing, fallback, and directive links.
8. Redacted conversation/tool payloads.
9. Replay and bidirectional pivots.

Do not show a polished content panel for data the evidence plane cannot prove. A degraded state is better than a visually complete but false inspector.

Exit gate:

- P.2 must-fix checklist is closed or residual risk is visible;
- golden trace fixture proves every join;
- hostile-content rendering tests pass;
- cross-tenant lookup returns the required safe result;
- visual and accessibility snapshots pass.

### Phase 6 — Sessions, incidents, directives, and billing

**Maps to:** 4.D.3 through 4.D.6.

Implement in this order because it follows data maturity:

1. Sessions and memory evidence;
2. incidents and evidence bundles;
3. directives/routing/controlled actions;
4. usage, cost, and capacity.

Each domain follows the same pattern:

```text
mock page contract
  → real API DTO
  → repository service/query
  → tenant/security tests
  → deterministic fixture matching the DTO
  → page wiring
  → visual/accessibility/e2e gates
```

Drift remains behind the Phase 4.5 producer contract. Billing keeps estimated and reconciled actual values visibly separate until reconciliation is complete.

### Phase 7 — Release and retirement

**Maps to:** 4.P.5, 4.P.6, Track E.

When console has topology parity and the required routes are real:

- deploy it through the application Helm/compose topology;
- add probes, limits, PDBs, network policy, and immutable image digests;
- add operator-origin smoke tests;
- run the four-role/two-tenant Playwright matrix;
- run axe and keyboard suites;
- run load, slow-client, SSE drain, provider failure, backup/restore, and rollback scenarios;
- publish visual, contract, security, and reliability evidence;
- retire `services/dashboard` only after migration parity is proven.

---

## 6. Testing and quality gates

### 6.1 Required checks on every pull request

```text
pnpm --filter console lint
pnpm --filter console typecheck
pnpm --filter console test
pnpm --filter console test:visual
pnpm --filter console test:a11y
pnpm --filter console test:e2e:smoke
pnpm --filter console build
```

Add API contract checks alongside the front end:

```text
OpenAPI snapshot diff
Generated client freshness
DTO runtime validation tests
Cross-tenant authorization tests
Operator session/CSRF tests
```

### 6.2 Visual regression policy

Visual tests should cover:

- Overview, Explore, Trace Inspector, sessions, incidents, directives, billing, settings;
- light/dark modes;
- 1440px desktop, 1024px tablet, and 390px mobile;
- sidebar expanded and collapsed;
- loading, empty, partial, stale, degraded, forbidden, and step-up states;
- long IDs, long error messages, empty tables, and large numbers;
- reduced-motion mode.

A visual diff is not automatically a failure when the design contract intentionally changes, but the change must include:

- updated screenshot;
- reason;
- affected routes;
- accessibility review;
- confirmation that the change did not come from a backend loading state or accidental CSS drift.

### 6.3 Determinism checks

Add lint or static checks for:

- `Math.random()` in render paths;
- uncontrolled `Date.now()`/`new Date()` in view logic;
- direct `fetch` from page components;
- fixture imports from production API modules;
- localStorage use for authoritative server state;
- hidden permission-denied states;
- unbounded client-side retries;
- raw prompt/tool rendering without the safe renderer.

### 6.4 Accessibility checks

Every slice must include:

- keyboard-only navigation;
- visible focus state;
- semantic headings and landmarks;
- screen-reader-visible state changes;
- accessible chart summaries or tables;
- modal focus trapping and return focus;
- no color-only status meaning;
- reduced-motion support;
- axe scan with zero serious/critical findings.

### 6.5 Performance checks

Measure the actual operator experience, not only a synthetic static page:

- initial shell load;
- Overview first meaningful data;
- Explore query response and rendering;
- Trace Inspector detail open;
- SSE connection and reconnect;
- large table virtualization or pagination;
- slow/degraded API behavior.

Keep heavy charts, trace panels, and replay controls behind client boundaries and lazy loading, while preserving immediate shell and status rendering.

---

## 7. Rules for using AI or multiple contributors without losing quality

The design loss happens when each contributor independently interprets a milestone. Enforce these rules:

1. **Never assign “build D2” as an unbounded task.** Assign a page contract, API DTO, fixture, screenshot baseline, and test matrix.
2. **Provide the contributor with the exact mock route and components.** The task is to wire or extract, not invent a new UI.
3. **Require a before/after screenshot comparison.** No visual change is accepted from code review alone.
4. **Require the data-state matrix.** Every response state must be implemented explicitly.
5. **Require a contract diff.** Any new field or API behavior must be documented.
6. **Keep domain migrations small.** One page family at a time; never simultaneously rewrite shell, styles, API, and routing.
7. **Do not accept “looks close.”** Compare against the baseline at the target viewports.
8. **Do not let fixture convenience define the production contract.** The backend contract is authoritative once published.
9. **Do not hide unavailable data.** Show it as unavailable or partial using the mock’s established language.
10. **Keep a visual decision log.** Record intentional changes so later work does not re-litigate or accidentally reverse them.

A good implementation task should look like this:

```text
Route: /dashboard/explore/t/[traceId]
Mock reference: component and screenshot IDs
Question: Why did this inference use these memories?
API: GET /v1/operator/traces/{trace_id}
DTO: TraceInspectorV1
States: loading, complete, partial, forbidden, expired, unavailable
Security: org scope, safe rendering, redacted payloads
Tests: golden trace, cross-tenant 404, axe, visual desktop/mobile
Rollback: metadata-only mode
```

---

## 8. Definition of “real quality”

A route is not complete because it compiles or because it resembles the mock. It is complete when all of these are true:

### Product quality

- The route answers a clear operator question.
- The design matches the approved mock baseline.
- It works at desktop, tablet, and mobile widths.
- All data states are visible and understandable.
- Navigation and deep links preserve context.

### Engineering quality

- It uses Server Components and client islands appropriately.
- It consumes a versioned typed DTO.
- It has no fixture path in production mode.
- It handles timeout, stale, partial, forbidden, and unavailable responses.
- It has stable telemetry and request IDs.

### Security quality

- Tenant scope is server-enforced.
- Permissions and step-up requirements are authoritative.
- Raw secrets and sensitive content are not logged or exposed.
- Hostile content is safely rendered.
- Mutations are idempotent/audited where required.

### Evidence quality

- The UI never claims data that the evidence plane cannot prove.
- Provenance joins are stable and copyable.
- Freshness, completeness, sampling, and retention are shown.
- The golden fixture proves the displayed relationship.

### Release quality

- Lint, typecheck, unit, contract, visual, accessibility, E2E, and build gates pass.
- Rollback can disable the route or degrade it safely.
- The route has operational metrics and runbook coverage.

---

## 9. Immediate next actions

The next implementation should be a dedicated **console foundation PR series**, not another isolated milestone attempt:

### PR 1 — Seed and freeze

- Add `services/console` from the mock.
- Add workspace/config/build scripts.
- Preserve the mock routes and visual output.
- Fix deterministic-render and high-value lint issues.
- Add screenshot baseline scaffolding.

### PR 2 — Shared quality infrastructure

- Add API client boundary.
- Add runtime DTO validation.
- Add deterministic clock and fixture factories.
- Add data-state components.
- Add visual and accessibility test harness.
- Add production/preview/test mode separation.

### PR 3 — Real shell

- Integrate operator session cookies, CSRF, logout, refresh, and session expiry.
- Integrate org context and tenant-safe org switching.
- Integrate platform health and SSE connection state.
- Preserve the mock shell exactly.

### PR 4 — D1 Overview

- Add real Overview DTO and API.
- Replace Overview fixtures only.
- Keep all page structure and styling from the mock.
- Add the D1 acceptance matrix and evidence.

### PR 5 — Settings and governance

- Connect existing organization, user, agent, token, provider, privacy, legal-hold, and audit APIs.
- Prove permission, step-up, and cross-tenant behavior.

### PR 6 onward — Evidence-driven Track D slices

- Explore and Trace Inspector;
- sessions and replay evidence;
- incidents and bundles;
- directives and controlled actions;
- cost, governance, and capacity.

Each PR should be independently reviewable, screenshot-tested, contract-tested, and rollback-safe.

---

## Final recommendation

The mock dashboard should become the **canonical operator product baseline**. Do not ask milestone implementers to recreate it from prose. Give them a route, a screenshot, a component contract, a DTO, a state matrix, and a test matrix.

The main repository should provide the truth underneath that surface:

- FastAPI/OpenAPI for contracts;
- PostgreSQL/ClickHouse/Redis for durable and queryable data;
- operator sessions and tenant authorization for access;
- evidence outbox and provenance for explainability;
- billing and enforcement services for governance;
- Helm, probes, and CI for operation.

The short version is:

> **Transplant the mock first. Freeze the design. Add a typed API boundary. Replace fixtures one vertical slice at a time. Require visual, accessibility, contract, security, and rollback evidence for every slice.**

That is how the repository gets the mock’s exact quality without turning the mock’s simulated data into accidental production behavior.
